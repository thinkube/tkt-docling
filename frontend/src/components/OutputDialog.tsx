/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { useEffect, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { TkButton } from 'thinkube-style/components/buttons-badges';
import {
  TkDialogContent,
  TkDialogDescription,
  TkDialogHeader,
  TkDialogRoot,
  TkDialogTitle,
} from 'thinkube-style/components/modals-overlays';
import { TkErrorAlert } from 'thinkube-style/components/feedback';
import { useConversionsStore, type Conversion } from '@/stores/useConversionsStore';

// Previews longer than this are cut; the download has the whole file.
const PREVIEW_CHARS = 200_000;

interface OutputDialogProps {
  conversion: Conversion | null;
  format: string | null;
  onClose: () => void;
}

function OutputPreview({ conversionId, format }: { conversionId: string; format: string }) {
  const { t } = useTranslation();
  const fetchOutput = useConversionsStore((s) => s.fetchOutput);
  const [content, setContent] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchOutput(conversionId, format)
      .then(setContent)
      .catch(() => setFailed(true));
  }, [conversionId, format, fetchOutput]);

  if (failed) return <TkErrorAlert>{t('conversions.previewFailed')}</TkErrorAlert>;
  if (content === null) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="text-primary h-6 w-6 animate-spin" />
      </div>
    );
  }
  return (
    <pre data-testid="output-preview" className="bg-muted max-h-[60vh] overflow-auto p-4 text-xs whitespace-pre-wrap">
      {content.slice(0, PREVIEW_CHARS)}
    </pre>
  );
}

export function OutputDialog({ conversion, format, onClose }: OutputDialogProps) {
  const { t } = useTranslation();
  const downloadOutput = useConversionsStore((s) => s.downloadOutput);

  const download = () => {
    if (!conversion || !format) return;
    downloadOutput(conversion.id, format).catch(() => toast.error(t('conversions.downloadFailed')));
  };

  return (
    <TkDialogRoot open={!!conversion && !!format} onOpenChange={(next) => !next && onClose()}>
      <TkDialogContent className="max-w-5xl">
        <TkDialogHeader>
          <TkDialogTitle>
            {conversion?.filename} · {format && t(`conversions.formatNames.${format}`)}
          </TkDialogTitle>
          <TkDialogDescription>{t('conversions.previewDescription')}</TkDialogDescription>
        </TkDialogHeader>
        {conversion && format && (
          // Keyed so each output opens with an empty preview of its own.
          <OutputPreview key={`${conversion.id}/${format}`} conversionId={conversion.id} format={format} />
        )}
        <div className="flex justify-end">
          <TkButton onClick={download}>
            <Download className="h-4 w-4" />
            {t('conversions.download')}
          </TkButton>
        </div>
      </TkDialogContent>
    </TkDialogRoot>
  );
}
