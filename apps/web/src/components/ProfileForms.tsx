import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api, errorMessage } from "@/api/client";
import type { Profile } from "@/api/types";
import { humanize, splitList } from "@/lib/format";
import {
  EDUCATION_LEVELS,
  EMPLOYMENT_TYPES,
  preferencesSchema,
  profileBasicsSchema,
  REMOTE_PREFS,
  type Preferences,
  type PreferencesInput,
  type ProfileBasics,
  type ProfileBasicsInput,
} from "@/lib/schemas";
import { useToast } from "./Toast";
import { Button, Field, Input, Select } from "./ui";

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<Profile>) => api.patch<Profile>("/api/profile", patch),
    onSuccess: (p) => {
      qc.setQueryData(["profile"], p);
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function BasicsForm({
  profile,
  submitLabel = "Save",
  extra,
  onSaved,
}: {
  profile: Profile;
  submitLabel?: string;
  extra?: Partial<Profile>;
  onSaved?: () => void;
}) {
  const save = useSaveProfile();
  const toast = useToast();
  const form = useForm<ProfileBasicsInput, unknown, ProfileBasics>({
    resolver: zodResolver(profileBasicsSchema),
    defaultValues: {
      full_name: profile.full_name,
      headline: profile.headline,
      location: profile.location,
      years_experience: profile.years_experience ?? 0,
      education_level: (profile.education_level as ProfileBasics["education_level"]) ?? "bachelor",
    },
  });
  const errs = form.formState.errors;
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      await save.mutateAsync({ ...v, ...extra });
      onSaved?.();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  });
  return (
    <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
      <Field label="Full name" error={errs.full_name?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} autoComplete="name" {...form.register("full_name")} />}
      </Field>
      <Field label="Headline" hint="e.g. Data Scientist" error={errs.headline?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} {...form.register("headline")} />}
      </Field>
      <Field label="Location" error={errs.location?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} autoComplete="address-level2" {...form.register("location")} />}
      </Field>
      <Field label="Years of experience" error={errs.years_experience?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} type="number" step="0.5" min={0} max={60} {...form.register("years_experience")} />}
      </Field>
      <Field label="Highest education" error={errs.education_level?.message}>
        {(id, d) => (
          <Select id={id} aria-describedby={d} {...form.register("education_level")}>
            {EDUCATION_LEVELS.map((l) => (
              <option key={l} value={l}>
                {humanize(l)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <div className="flex items-end justify-end sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

export function PreferencesForm({
  profile,
  submitLabel = "Save",
  extra,
  onSaved,
}: {
  profile: Profile;
  submitLabel?: string;
  extra?: Partial<Profile>;
  onSaved?: () => void;
}) {
  const save = useSaveProfile();
  const toast = useToast();
  const form = useForm<PreferencesInput, unknown, Preferences>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: {
      target_titles: profile.target_titles.join(", "),
      preferred_locations: profile.preferred_locations.join(", "),
      remote_preference: (profile.remote_preference as Preferences["remote_preference"]) || "any",
      employment_types: (profile.employment_types.length ? profile.employment_types : ["full_time"]) as Preferences["employment_types"],
      min_salary: profile.min_salary ?? "",
      blocked_companies: profile.blocked_companies.join(", "),
      blocked_keywords: profile.blocked_keywords.join(", "),
      experience_filter_mode: profile.experience_filter_mode,
    },
  });
  const errs = form.formState.errors;
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      await save.mutateAsync({
        target_titles: splitList(v.target_titles),
        preferred_locations: splitList(v.preferred_locations),
        remote_preference: v.remote_preference,
        employment_types: v.employment_types,
        min_salary: v.min_salary === "" ? null : v.min_salary,
        blocked_companies: splitList(v.blocked_companies),
        blocked_keywords: splitList(v.blocked_keywords),
        experience_filter_mode: v.experience_filter_mode,
        ...extra,
      });
      onSaved?.();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  });
  return (
    <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
      <Field label="Target job titles" hint="Comma-separated" error={errs.target_titles?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} placeholder="Data Scientist, ML Engineer" {...form.register("target_titles")} />}
      </Field>
      <Field label="Preferred locations" hint="Comma-separated; include “Remote” if you want remote roles">
        {(id, d) => <Input id={id} aria-describedby={d} {...form.register("preferred_locations")} />}
      </Field>
      <Field label="Remote preference">
        {(id) => (
          <Select id={id} {...form.register("remote_preference")}>
            {REMOTE_PREFS.map((r) => (
              <option key={r} value={r}>
                {humanize(r)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Minimum salary (optional)" hint="Jobs that state a lower maximum are filtered out" error={errs.min_salary?.message}>
        {(id, d) => <Input id={id} aria-describedby={d} type="number" min={0} {...form.register("min_salary")} />}
      </Field>
      <fieldset className="sm:col-span-2">
        <legend className="mb-1 text-sm font-medium">Employment types</legend>
        <div className="flex flex-wrap gap-4">
          {EMPLOYMENT_TYPES.map((t) => (
            <label key={t} className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" value={t} className="h-4 w-4 accent-[rgb(var(--primary))]" {...form.register("employment_types")} />
              {humanize(t)}
            </label>
          ))}
        </div>
        {errs.employment_types && (
          <p role="alert" className="mt-1 text-xs text-danger">
            {errs.employment_types.message}
          </p>
        )}
      </fieldset>
      <Field label="Blocked companies" hint="Comma-separated; never shown as matches">
        {(id, d) => <Input id={id} aria-describedby={d} {...form.register("blocked_companies")} />}
      </Field>
      <Field label="Blocked keywords" hint="Comma-separated">
        {(id, d) => <Input id={id} aria-describedby={d} {...form.register("blocked_keywords")} />}
      </Field>
      <Field label="Experience requirement" hint="Hard: postings asking for more years than you have are filtered out">
        {(id, d) => (
          <Select id={id} aria-describedby={d} {...form.register("experience_filter_mode")}>
            <option value="soft">Soft (lower the score)</option>
            <option value="hard">Hard (filter out)</option>
          </Select>
        )}
      </Field>
      <div className="flex items-end justify-end">
        <Button type="submit" loading={save.isPending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
