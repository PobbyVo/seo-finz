import type { Metadata, Viewport } from 'next';
import './globals.css';
import { ProjectProvider } from '@/context/ProjectContext';
import { AppShell } from '@/components/AppShell';
import { FormAriaSync } from '@/components/FormAriaSync';

export const metadata: Metadata = {
  title: 'FinZ SEO Workbench V1.6 — Hệ thống quyết định SEO có kiểm chứng',
  description:
    'Ứng dụng web local dark-mode hỗ trợ chuyên viên SEO phân tích nhu cầu, đối chiếu bằng chứng Semrush, phê duyệt Keyword Mapping và xuất Content Brief.',
};

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#07090f',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className="dark">
      <head>
        <meta name="color-scheme" content="dark" />
      </head>
      <body className="bg-surface-950 text-slate-100 antialiased selection:bg-sky-500/30 selection:text-sky-100">
        <ProjectProvider>
          <FormAriaSync />
          <AppShell>{children}</AppShell>
        </ProjectProvider>
      </body>
    </html>
  );
}
