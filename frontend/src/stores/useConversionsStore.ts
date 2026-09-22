/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { create } from 'zustand';
import api from '@/lib/axios';

export type ConversionStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface Conversion {
  id: string;
  filename: string;
  size_bytes: number;
  pipeline: string;
  formats: string[];
  status: ConversionStatus;
  error?: string | null;
  pages?: number | null;
  seconds?: number | null;
  workflow_name?: string | null;
  logs_url?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface OutputFormat {
  name: string;
  filename: string;
  description: string;
}

export interface Pipeline {
  name: string;
  description: string;
  available: boolean;
  unavailable_reason?: string | null;
}

export interface Options {
  formats: OutputFormat[];
  pipelines: Pipeline[];
  max_upload_mb: number;
}

export interface ConversionInput {
  file: File;
  pipeline: string;
  formats: string[];
}

export const isFinished = (c: Conversion) => c.status === 'succeeded' || c.status === 'failed';

interface ConversionsState {
  conversions: Conversion[];
  options: Options | null;
  loading: boolean;
  error: string | null;

  fetchOptions: () => Promise<void>;
  fetchConversions: () => Promise<void>;
  createConversion: (input: ConversionInput) => Promise<Conversion>;
  deleteConversion: (id: string) => Promise<void>;
  fetchOutput: (id: string, format: string) => Promise<string>;
  downloadOutput: (id: string, format: string) => Promise<void>;
}

export const useConversionsStore = create<ConversionsState>((set, get) => ({
  conversions: [],
  options: null,
  loading: false,
  error: null,

  fetchOptions: async () => {
    const response = await api.get<Options>('/conversions/options');
    set({ options: response.data });
  },

  fetchConversions: async () => {
    set({ loading: true, error: null });
    try {
      const response = await api.get<Conversion[]>('/conversions');
      set({ conversions: response.data, loading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch conversions',
        loading: false,
      });
      throw err;
    }
  },

  createConversion: async ({ file, pipeline, formats }) => {
    const body = new FormData();
    body.append('file', file);
    body.append('pipeline', pipeline);
    body.append('formats', formats.join(','));
    // An upload of a large PDF takes longer than the client's default timeout.
    const response = await api.post<Conversion>('/conversions', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 0,
    });
    await get().fetchConversions();
    return response.data;
  },

  deleteConversion: async (id) => {
    await api.delete(`/conversions/${id}`);
    await get().fetchConversions();
  },

  fetchOutput: async (id, format) => {
    const response = await api.get<string>(`/conversions/${id}/outputs/${format}`, {
      responseType: 'text',
      transformResponse: (data) => data,
    });
    return response.data;
  },

  // The API needs the bearer token, so a plain link cannot fetch the file:
  // it is fetched here and handed to the browser as a local object URL.
  downloadOutput: async (id, format) => {
    const response = await api.get<Blob>(`/conversions/${id}/outputs/${format}`, {
      params: { download: true },
      responseType: 'blob',
    });
    const disposition = String(response.headers['content-disposition'] ?? '');
    const match = /filename="([^"]+)"/.exec(disposition);
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = match ? match[1] : `${id}-${format}`;
    link.click();
    URL.revokeObjectURL(url);
  },
}));
