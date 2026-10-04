/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { useEffect, useState } from 'react';
import { ExternalLink, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { TkBadge, TkButton } from 'thinkube-style/components/buttons-badges';
import { TkErrorAlert, TkInfoAlert } from 'thinkube-style/components/feedback';
import { TkControlledConfirmDialog } from 'thinkube-style/components/modals-overlays';
import {
  TkTable,
  TkTableBody,
  TkTableCell,
  TkTableHead,
  TkTableHeader,
  TkTableRow,
} from 'thinkube-style/components/tables';
import { TkPageWrapper } from 'thinkube-style/components/utilities';
import { NewConversionCard } from '@/components/NewConversionCard';
import { OutputDialog } from '@/components/OutputDialog';
import { isFinished, useConversionsStore, type Conversion } from '@/stores/useConversionsStore';

// While a conversion runs, the list is read again at this interval.
export const POLL_MS = 5000;

const STATUS_BADGE = {
  queued: 'pending',
  running: 'active',
  succeeded: 'healthy',
  failed: 'unhealthy',
} as const;

export default function ConversionsPage() {
  const { t, i18n } = useTranslation();
  const { conversions, options, loading, fetchOptions, fetchConversions, deleteConversion } =
    useConversionsStore();
  const [preview, setPreview] = useState<{ conversion: Conversion; format: string } | null>(null);
  const [toDelete, setToDelete] = useState<Conversion | null>(null);

  useEffect(() => {
    fetchOptions().catch(() => toast.error(t('conversions.optionsFailed')));
    fetchConversions().catch(() => toast.error(t('conversions.loadFailed')));
  }, [fetchOptions, fetchConversions, t]);

  const anyRunning = conversions.some((c) => !isFinished(c));
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => {
      fetchConversions().catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [anyRunning, fetchConversions]);

  const confirmDelete = async () => {
    if (!toDelete) return;
    try {
      await deleteConversion(toDelete.id);
      toast.success(t('conversions.deleted'));
    } catch {
      toast.error(t('conversions.deleteFailed'));
    } finally {
      setToDelete(null);
    }
  };

  const formatDate = (value: string) => new Date(value + 'Z').toLocaleString(i18n.resolvedLanguage);

  return (
    <TkPageWrapper>
      <div>
        <h1 className="text-2xl font-bold">{t('conversions.title')}</h1>
        <p className="text-muted-foreground mt-1">{t('conversions.subtitle')}</p>
      </div>

      {options && <NewConversionCard options={options} />}

      <h2 className="text-xl font-semibold">{t('conversions.listTitle')}</h2>
      {loading && conversions.length === 0 ? (
        <div className="flex justify-center py-12">
          <Loader2 className="text-primary h-8 w-8 animate-spin" />
        </div>
      ) : conversions.length === 0 ? (
        <TkInfoAlert>{t('conversions.empty')}</TkInfoAlert>
      ) : (
        <TkTable>
          <TkTableHeader>
            <TkTableRow>
              <TkTableHead>{t('conversions.table.file')}</TkTableHead>
              <TkTableHead>{t('conversions.table.pipeline')}</TkTableHead>
              <TkTableHead>{t('conversions.table.status')}</TkTableHead>
              <TkTableHead>{t('conversions.table.outputs')}</TkTableHead>
              <TkTableHead />
            </TkTableRow>
          </TkTableHeader>
          <TkTableBody>
            {conversions.map((c) => (
              <TkTableRow key={c.id} data-testid="conversion-row">
                <TkTableCell>
                  <div className="font-medium">{c.filename}</div>
                  <div className="text-muted-foreground text-xs">{formatDate(c.created_at)}</div>
                </TkTableCell>
                <TkTableCell>{t(`conversions.pipelines.${c.pipeline}`)}</TkTableCell>
                <TkTableCell>
                  <TkBadge status={STATUS_BADGE[c.status]}>{t(`conversions.status.${c.status}`)}</TkBadge>
                  {c.status === 'succeeded' && (
                    <div className="text-muted-foreground mt-1 text-xs">
                      {t('conversions.pagesIn', { pages: c.pages, seconds: c.seconds })}
                    </div>
                  )}
                  {c.status === 'failed' && c.error && (
                    <TkErrorAlert className="mt-2">{c.error}</TkErrorAlert>
                  )}
                </TkTableCell>
                <TkTableCell>
                  <div className="flex flex-wrap gap-1">
                    {c.formats.map((format) => (
                      <TkButton
                        key={format}
                        size="sm"
                        intent="secondary"
                        disabled={c.status !== 'succeeded'}
                        onClick={() => setPreview({ conversion: c, format })}
                      >
                        {t(`conversions.formatNames.${format}`)}
                      </TkButton>
                    ))}
                  </div>
                </TkTableCell>
                <TkTableCell>
                  <div className="flex justify-end gap-1">
                    {c.logs_url && (
                      <TkButton asChild size="icon" intent="ghost" title={t('conversions.logs')}>
                        <a href={c.logs_url} target="_blank" rel="noreferrer" aria-label={t('conversions.logs')}>
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </TkButton>
                    )}
                    <TkButton
                      size="icon"
                      intent="ghost"
                      aria-label={t('common.delete')}
                      onClick={() => setToDelete(c)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </TkButton>
                  </div>
                </TkTableCell>
              </TkTableRow>
            ))}
          </TkTableBody>
        </TkTable>
      )}

      <OutputDialog
        conversion={preview?.conversion ?? null}
        format={preview?.format ?? null}
        onClose={() => setPreview(null)}
      />

      <TkControlledConfirmDialog
        open={!!toDelete}
        onOpenChange={(open) => !open && setToDelete(null)}
        title={t('conversions.confirmDeleteTitle')}
        description={t('conversions.confirmDelete', { name: toDelete?.filename })}
        confirmText={t('common.delete')}
        cancelText={t('common.cancel')}
        variant="destructive"
        onConfirm={confirmDelete}
      />
    </TkPageWrapper>
  );
}
