/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { isAxiosError } from 'axios';
import { TkLoadingButton } from 'thinkube-style/components/buttons-badges';
import {
  TkCard,
  TkCardContent,
  TkCardDescription,
  TkCardHeader,
  TkCardTitle,
} from 'thinkube-style/components/cards-data';
import {
  TkCheckbox,
  TkDropZone,
  TkLabel,
  TkRadioGroup,
  TkRadioGroupItem,
} from 'thinkube-style/components/forms-inputs';
import { TkWarningAlert } from 'thinkube-style/components/feedback';
import { useConversionsStore, type Options } from '@/stores/useConversionsStore';

const DEFAULT_FORMATS = ['markdown', 'jats'];

export function NewConversionCard({ options }: { options: Options }) {
  const { t } = useTranslation();
  const createConversion = useConversionsStore((s) => s.createConversion);
  const [files, setFiles] = useState<File[]>([]);
  const [pipeline, setPipeline] = useState('standard');
  const [formats, setFormats] = useState<string[]>(DEFAULT_FORMATS);
  const [submitting, setSubmitting] = useState(false);

  const unavailable = options.pipelines.find((p) => p.name === pipeline && !p.available);

  const toggleFormat = (name: string, checked: boolean) =>
    setFormats((current) => (checked ? [...current, name] : current.filter((f) => f !== name)));

  const tooLarge = files.length > 0 && files[0].size > options.max_upload_mb * 1024 * 1024;
  const canSubmit = files.length === 1 && formats.length > 0 && !unavailable && !tooLarge;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      // Formats in the order the API lists them.
      const ordered = options.formats.map((f) => f.name).filter((n) => formats.includes(n));
      await createConversion({ file: files[0], pipeline, formats: ordered });
      toast.success(t('conversions.started', { name: files[0].name }));
      setFiles([]);
    } catch (err) {
      const detail = isAxiosError(err) ? err.response?.data?.detail : null;
      toast.error(typeof detail === 'string' ? detail : t('conversions.startFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <TkCard>
      <TkCardHeader>
        <TkCardTitle>{t('conversions.newTitle')}</TkCardTitle>
        <TkCardDescription>{t('conversions.newSubtitle', { mb: options.max_upload_mb })}</TkCardDescription>
      </TkCardHeader>
      <TkCardContent className="space-y-6">
        <TkDropZone label={t('conversions.pdf')} accept=".pdf" files={files} onFilesChange={setFiles} required />
        {tooLarge && (
          <TkWarningAlert>{t('conversions.tooLarge', { mb: options.max_upload_mb })}</TkWarningAlert>
        )}

        <div className="grid gap-6 md:grid-cols-2">
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">{t('conversions.pipeline')}</legend>
            <TkRadioGroup value={pipeline} onValueChange={setPipeline}>
              {options.pipelines.map((p) => (
                <div key={p.name} className="flex items-start gap-2">
                  <TkRadioGroupItem id={`pipeline-${p.name}`} value={p.name} />
                  <TkLabel htmlFor={`pipeline-${p.name}`} className="grid gap-1 font-normal">
                    <span className="font-medium">{t(`conversions.pipelines.${p.name}`)}</span>
                    <span className="text-muted-foreground text-xs">{p.description}</span>
                  </TkLabel>
                </div>
              ))}
            </TkRadioGroup>
            {unavailable && <TkWarningAlert>{unavailable.unavailable_reason}</TkWarningAlert>}
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">{t('conversions.formats')}</legend>
            {options.formats.map((f) => (
              <div key={f.name} className="flex items-start gap-2">
                <TkCheckbox
                  id={`format-${f.name}`}
                  checked={formats.includes(f.name)}
                  onCheckedChange={(checked) => toggleFormat(f.name, checked === true)}
                />
                <TkLabel htmlFor={`format-${f.name}`} className="grid gap-1 font-normal">
                  <span className="font-medium">{t(`conversions.formatNames.${f.name}`)}</span>
                  <span className="text-muted-foreground text-xs">{f.description}</span>
                </TkLabel>
              </div>
            ))}
          </fieldset>
        </div>

        <TkLoadingButton onClick={submit} disabled={!canSubmit} loading={submitting}>
          {t('conversions.convert')}
        </TkLoadingButton>
      </TkCardContent>
    </TkCard>
  );
}
