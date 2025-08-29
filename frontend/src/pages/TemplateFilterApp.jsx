import React, { useEffect, useMemo, useRef, useState } from "react";
import { Upload, Database, Send, FileText, CheckCircle2, HelpCircle, ListChecks, MessageSquarePlus, PlugZap, FileDown } from "lucide-react";

export default function TemplateFillerApp() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white text-gray-900">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <header className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <FileText className="h-6 w-6" /> 模組填空助手
          </h1>
          <div className="text-sm text-gray-500 flex items-center gap-2">
            <PlugIndicator /> 支援 WebSocket 流式/逐題詢問 + 匯出
          </div>
        </header>

        <div className="grid gap-6 md:grid-cols-3">
          <section className="md:col-span-1 space-y-6">
            <ModuleUploader />
            <ModulePicker />
          </section>

          <section className="md:col-span-2 space-y-6">
            <TemplateOverview />
            <ChatFiller />
          </section>
        </div>
      </div>
    </div>
  );
}
/* ... (trimmed in generator: full content is same as prior message) ... */
