/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConversionsPage, { POLL_MS } from '../ConversionsPage';
import api from '@/lib/axios';
import { useConversionsStore, type Conversion, type Options } from '@/stores/useConversionsStore';

vi.mock('@/lib/axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const options: Options = {
  formats: [
    { name: 'markdown', filename: 'document.md', description: 'Markdown with tables' },
    { name: 'html', filename: 'document.html', description: 'HTML page' },
    { name: 'jats', filename: 'document.jats.xml', description: 'JATS XML (Archiving 1.4)' },
  ],
  pipelines: [
    { name: 'standard', description: 'Layout and table models on CPU', available: true },
    { name: 'granite-docling', description: 'Through the LLM Gateway', available: true },
  ],
  max_upload_mb: 100,
};

const done: Conversion = {
  id: 'c-1',
  filename: 'pone.0297349.pdf',
  size_bytes: 1816268,
  pipeline: 'granite-docling',
  formats: ['markdown', 'jats'],
  status: 'succeeded',
  pages: 15,
  seconds: 14,
  workflow_name: 'docling-convert-abcde',
  logs_url: 'https://argo.example.com/workflows/docling/docling-convert-abcde',
  created_at: '2026-09-17T13:40:00',
  finished_at: '2026-09-17T13:40:30',
};

function serve(conversions: Conversion[] | (() => Conversion[])) {
  mockedApi.get.mockImplementation(async (url: string) => {
    if (url === '/conversions/options') return { data: options };
    if (url === '/conversions') return { data: typeof conversions === 'function' ? conversions() : conversions };
    if (url.startsWith('/conversions/c-1/outputs/')) return { data: '<article dtd-version="1.4"/>' };
    throw new Error(`unexpected GET ${url}`);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useConversionsStore.setState({ conversions: [], options: null, loading: false, error: null });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ConversionsPage', () => {
  it('shows the empty state and the form with pipelines and formats', async () => {
    serve([]);
    render(<ConversionsPage />);

    expect(await screen.findByText('No conversions yet. Upload a PDF above.')).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: /Granite-Docling/ })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /JATS XML/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /HTML/ })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Convert' })).toBeDisabled();
  });

  it('uploads a PDF with the chosen pipeline and formats', async () => {
    const user = userEvent.setup();
    serve([]);
    mockedApi.post.mockResolvedValue({ data: { ...done, status: 'queued' } });
    const { container } = render(<ConversionsPage />);
    await screen.findByRole('radio', { name: /Granite-Docling/ });

    const pdf = new File(['%PDF-1.7'], 'paper.pdf', { type: 'application/pdf' });
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, pdf);
    await user.click(screen.getByRole('radio', { name: /Granite-Docling/ }));
    await user.click(screen.getByRole('checkbox', { name: /HTML/ }));
    await user.click(screen.getByRole('button', { name: 'Convert' }));

    await waitFor(() => expect(mockedApi.post).toHaveBeenCalledTimes(1));
    const [url, body] = mockedApi.post.mock.calls[0] as [string, FormData];
    expect(url).toBe('/conversions');
    expect(body.get('pipeline')).toBe('granite-docling');
    expect(body.get('formats')).toBe('markdown,html,jats');
    expect((body.get('file') as File).name).toBe('paper.pdf');
  });

  it('explains why a pipeline is unavailable and blocks it', async () => {
    const user = userEvent.setup();
    const reason = 'THINKUBE_API_TOKEN is not set.';
    mockedApi.get.mockImplementation(async (url: string) => {
      if (url === '/conversions/options') {
        return {
          data: {
            ...options,
            pipelines: [options.pipelines[0], { ...options.pipelines[1], available: false, unavailable_reason: reason }],
          },
        };
      }
      return { data: [] };
    });
    render(<ConversionsPage />);

    await user.click(await screen.findByRole('radio', { name: /Granite-Docling/ }));
    expect(screen.getByText(reason)).toBeInTheDocument();
  });

  it('lists conversions with their status and opens an output', async () => {
    const user = userEvent.setup();
    serve([done, { ...done, id: 'c-2', filename: 'broken.pdf', status: 'failed', error: 'OOMKilled' }]);
    render(<ConversionsPage />);

    const rows = await screen.findAllByTestId('conversion-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Done')).toBeInTheDocument();
    expect(within(rows[0]).getByText('15 pages in 14 s')).toBeInTheDocument();
    expect(within(rows[1]).getByText('OOMKilled')).toBeInTheDocument();
    expect(within(rows[1]).getByRole('button', { name: 'JATS XML' })).toBeDisabled();

    await user.click(within(rows[0]).getByRole('button', { name: 'JATS XML' }));
    expect(await screen.findByTestId('output-preview')).toHaveTextContent('<article dtd-version="1.4"/>');
    expect(mockedApi.get).toHaveBeenCalledWith('/conversions/c-1/outputs/jats', expect.anything());
  });

  it('reads the list again while a conversion runs', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let status: Conversion['status'] = 'running';
    serve(() => [{ ...done, status }]);
    render(<ConversionsPage />);

    expect(await screen.findByText('Running')).toBeInTheDocument();
    status = 'succeeded';
    await act(async () => {
      vi.advanceTimersByTime(POLL_MS);
    });
    expect(await screen.findByText('Done')).toBeInTheDocument();
  });

  it('deletes a conversion after confirmation', async () => {
    const user = userEvent.setup();
    serve([done]);
    mockedApi.delete.mockResolvedValue({ data: {} });
    render(<ConversionsPage />);

    const row = await screen.findByTestId('conversion-row');
    await user.click(within(row).getByRole('button', { name: 'Delete' }));
    const dialog = await screen.findByRole('alertdialog').catch(() => screen.findByRole('dialog'));
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mockedApi.delete).toHaveBeenCalledWith('/conversions/c-1'));
  });
});
