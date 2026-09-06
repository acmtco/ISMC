import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const REASONS = [
  { value: "out_of_frame", label: "Техника вне кадра" },
  { value: "wrong_norm", label: "Неверная норма в графике" },
  { value: "recognition_error", label: "Ошибка распознавания" },
] as const;

/** docs/03-deviation-rules.md, шаг 5: обратная связь возвращает разметку в
 * калибровку порогов. Отдельного эндпоинта для этого в docs/02 §7 пока нет —
 * это заготовка формы; при появлении `POST /api/deviations/{id}/feedback`
 * здесь останется только заменить локальный `onSubmit` на вызов API. */
export function DisagreeDialog({ deviationId }: { deviationId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<(typeof REASONS)[number]["value"]>("out_of_frame");
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setSent(false);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">Не согласен</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Отклонение {deviationId}: не согласен</DialogTitle>
          <DialogDescription>
            Причина уйдёт в калибровку порогов — так система учится реже ошибаться.
          </DialogDescription>
        </DialogHeader>

        {sent ? (
          <p className="text-sm text-status-green">Спасибо, зафиксировано.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Причина</Label>
              <div className="flex flex-col gap-1.5">
                {REASONS.map((r) => (
                  <label key={r.value} className="flex items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="reason"
                      checked={reason === r.value}
                      onChange={() => setReason(r.value)}
                    />
                    {r.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Комментарий (необязательно)</Label>
              <Textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
            </div>
          </div>
        )}

        <DialogFooter>
          {sent ? (
            <Button variant="outline" onClick={() => setOpen(false)}>
              Закрыть
            </Button>
          ) : (
            <Button onClick={() => setSent(true)}>Отправить</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
