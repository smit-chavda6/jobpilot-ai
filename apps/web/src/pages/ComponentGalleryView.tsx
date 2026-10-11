import { useState } from "react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Modal } from "../components/ui/modal";
import { Check, AlertTriangle } from "lucide-react";

export function ComponentGalleryView() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");

  return (
    <div className="space-y-10 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Design System & Component Gallery</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Interactive showcase of core WCAG 2.2 AA compliant UI primitives and tokens for JobPilot AI.
        </p>
      </div>

      {/* Buttons Section */}
      <Card>
        <CardHeader>
          <CardTitle>Button Primitives</CardTitle>
          <CardDescription>Buttons across variants, sizes, and accessible loading states</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Primary Action</Button>
            <Button variant="secondary">Secondary Action</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="primary" isLoading>
              Saving Changes
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
            <Button size="sm">Small (sm)</Button>
            <Button size="md">Medium (md)</Button>
            <Button size="lg">Large (lg)</Button>
          </div>
        </CardContent>
      </Card>

      {/* Badges Section */}
      <Card>
        <CardHeader>
          <CardTitle>Semantic Badges & Match Scores</CardTitle>
          <CardDescription>Status indicators for match scoring, compliance, and application states</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2.5">
          <Badge variant="default">Verified Grounded</Badge>
          <Badge variant="success">96% High Fit</Badge>
          <Badge variant="warning">Needs User Input</Badge>
          <Badge variant="destructive">Missing Required Skill</Badge>
          <Badge variant="secondary">Remote Policy: Flexible</Badge>
          <Badge variant="outline">Manual Import</Badge>
        </CardContent>
      </Card>

      {/* Inputs Section */}
      <Card>
        <CardHeader>
          <CardTitle>Form Inputs & Accessible Validation</CardTitle>
          <CardDescription>Inputs with semantic label pairing and high contrast error messaging</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Input
            label="Target Job Title"
            placeholder="e.g. Senior Backend Engineer"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
          />
          <Input
            label="Minimum Annual Salary (USD)"
            placeholder="150000"
            error={inputValue.length > 0 && isNaN(Number(inputValue)) ? "Must be a valid positive number" : undefined}
          />
        </CardContent>
      </Card>

      {/* Modal / Dialog Trigger */}
      <Card>
        <CardHeader>
          <CardTitle>Accessible Dialog (Modal)</CardTitle>
          <CardDescription>Keyboard-trapped, focus-managed dialog with Escape dismiss</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => setIsModalOpen(true)}>
            Open Sample Approval Dialog
          </Button>

          <Modal
            isOpen={isModalOpen}
            onClose={() => setIsModalOpen(false)}
            title="Confirm Application Submission"
            description="Operating Principle #2: Human in the loop confirmation"
          >
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  This action marks the application status as confirmed. No unapproved background automated submission
                  will occur without your direct interaction.
                </span>
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Are you ready to submit your verified application materials to <strong>Stripe</strong>?
              </p>
              <div className="flex justify-end gap-2 pt-4">
                <Button variant="outline" size="sm" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => {
                    alert("Application submission approved and recorded!");
                    setIsModalOpen(false);
                  }}
                >
                  <Check className="w-4 h-4 mr-1" /> Explicitly Confirm Submission
                </Button>
              </div>
            </div>
          </Modal>
        </CardContent>
      </Card>
    </div>
  );
}
