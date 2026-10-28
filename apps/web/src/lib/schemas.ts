/**
 * Client-side validation that mirrors the API contracts (apps/api/app/routers/*, services/auth_service.py).
 * The server stays authoritative; these give instant feedback with the same rules and messages.
 */
import { z } from "zod";

export const passwordSchema = z
  .string()
  .min(10, "Password must be at least 10 characters")
  .max(256)
  .refine((p) => p.toLowerCase() !== p && /\d/.test(p), "Password needs at least one uppercase letter and one digit");

export const credentialsSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export const registerSchema = z
  .object({
    email: z.string().trim().email("Enter a valid email address"),
    password: passwordSchema,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });

export const resetSchema = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });

export const EDUCATION_LEVELS = ["none", "high_school", "associate", "bachelor", "master", "phd"] as const;
export const REMOTE_PREFS = ["any", "remote", "hybrid", "onsite"] as const;
export const EMPLOYMENT_TYPES = ["full_time", "part_time", "contract", "internship"] as const;

export const profileBasicsSchema = z.object({
  full_name: z.string().trim().min(1, "Enter your name").max(200),
  headline: z.string().max(300),
  location: z.string().max(200),
  years_experience: z.coerce.number().min(0, "Must be 0 or more").max(60, "Must be 60 or less"),
  education_level: z.enum(EDUCATION_LEVELS),
});

export const preferencesSchema = z.object({
  target_titles: z.string().min(1, "Add at least one target title"),
  preferred_locations: z.string(),
  remote_preference: z.enum(REMOTE_PREFS),
  employment_types: z.array(z.enum(EMPLOYMENT_TYPES)).min(1, "Pick at least one employment type"),
  min_salary: z.union([z.literal(""), z.coerce.number().int().min(0)]),
  blocked_companies: z.string(),
  blocked_keywords: z.string(),
  experience_filter_mode: z.enum(["soft", "hard"]),
});

export type ProfileBasics = z.infer<typeof profileBasicsSchema>;
export type Preferences = z.infer<typeof preferencesSchema>;
