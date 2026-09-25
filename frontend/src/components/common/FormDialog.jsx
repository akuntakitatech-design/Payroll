import React from "react";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export const Field = ({ field, value, onChange, error }) => {
  const id = `field-${field.name}`;
  const common = {
    id,
    "data-testid": `field-${field.name}`,
    "aria-invalid": !!error,
    "aria-describedby": error ? `${id}-error` : undefined,
    ...(field.disabled ? { disabled: true } : {}),
  };

  let control;
  if (field.type === "textarea") {
    control = (
      <Textarea
        {...common}
        rows={field.rows || 3}
        value={value ?? ""}
        placeholder={field.placeholder}
        onChange={(e) => onChange(field.name, e.target.value)}
      />
    );
  } else if (field.type === "boolean") {
    control = (
      <div className="flex h-9 items-center gap-2">
        <Switch
          id={id}
          data-testid={`field-${field.name}`}
          checked={!!value}
          onCheckedChange={(v) => onChange(field.name, v)}
        />
        <span className="text-sm text-muted-foreground">{value ? "Ya" : "Tidak"}</span>
      </div>
    );
  } else if (field.type === "select") {
    control = (
      <Select
        value={value ? String(value) : "__empty__"}
        onValueChange={(v) => onChange(field.name, v === "__empty__" ? "" : v)}
        disabled={!!field.disabled}
      >
        <SelectTrigger data-testid={`field-${field.name}`} id={id}>
          <SelectValue placeholder={field.placeholder || "Pilih…"} />
        </SelectTrigger>
        <SelectContent>
          {!field.required && <SelectItem value="__empty__">{field.emptyLabel || "— Tidak dipilih —"}</SelectItem>}
          {(field.options || []).map((opt) => (
            <SelectItem key={opt.value} value={String(opt.value)}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  } else {
    control = (
      <Input
        {...common}
        type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
        value={value ?? ""}
        placeholder={field.placeholder}
        onChange={(e) => onChange(field.name, e.target.value)}
      />
    );
  }

  return (
    <div className={cn("space-y-1.5", field.colSpan === 2 && "sm:col-span-2")}>
      <Label htmlFor={id} className="text-[13px] font-medium text-foreground">
        {field.label}
        {field.required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {control}
      {field.hint && !error && <p className="text-[12px] text-muted-foreground">{field.hint}</p>}
      {error && (
        <p id={`${id}-error`} className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
};

const FormDialog = ({
  open,
  onOpenChange,
  title,
  description,
  fields = [],
  values,
  errors = {},
  onChange,
  onSubmit,
  submitting,
  submitLabel = "Simpan",
  extra,
  wide = false,
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent
      data-testid="form-dialog"
      className={cn("max-h-[90vh] overflow-y-auto bg-card", wide ? "sm:max-w-3xl" : "sm:max-w-2xl")}
    >
      <DialogHeader>
        <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
        {description && <DialogDescription className="leading-relaxed">{description}</DialogDescription>}
      </DialogHeader>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="space-y-4"
      >
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
          {fields.map((field) => (
            <Field
              key={field.name}
              field={field}
              value={values?.[field.name]}
              error={errors?.[field.name]}
              onChange={onChange}
            />
          ))}
        </div>
        {extra}
        {errors?.__form__ && (
          <div
            className="rounded-md border border-danger-border bg-danger-soft px-3 py-2 text-[13px] text-danger"
            data-testid="form-dialog-error"
          >
            {errors.__form__}
          </div>
        )}
        <DialogFooter className="gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            data-testid="form-dialog-cancel-button"
          >
            Batal
          </Button>
          <Button type="submit" disabled={submitting} data-testid="form-dialog-submit-button">
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
);

export default FormDialog;
