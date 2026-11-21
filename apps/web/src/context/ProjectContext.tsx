'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';
import type { AIProviderInfo, ProjectItem } from '@/lib/types';

export interface CompletionPopupPayload {
  title: string;
  message: string;
  nextStepLabel?: string;
  nextStepHref?: string;
  navigationEligible: boolean;
}

interface ProjectContextValue {
  projects: ProjectItem[];
  activeProject: ProjectItem | null;
  activeProjectId: string | null;
  activeAI: AIProviderInfo | null;
  loading: boolean;
  setActiveProjectId: (id: string) => void;
  refreshProjects: (preferId?: string) => Promise<void>;
  refreshAISettings: () => Promise<void>;
  completionPopup: CompletionPopupPayload | null;
  showCompletionPopup: (payload: CompletionPopupPayload) => void;
  closeCompletionPopup: () => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);
const STORAGE_KEY = 'finz_active_project_id';

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [activeProjectId, setActiveProjectIdState] = useState<string | null>(null);
  const [activeAI, setActiveAI] = useState<AIProviderInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [completionPopup, setCompletionPopup] = useState<CompletionPopupPayload | null>(null);

  const refreshAISettings = useCallback(async () => {
    try {
      const data = await apiRequest<{ active_provider: string | null; providers: AIProviderInfo[] }>('/api/v1/settings/ai');
      const act = data.providers.find((p) => p.is_active) || null;
      setActiveAI(act);
    } catch {
      // keep previous state silently
    }
  }, []);

  const refreshProjects = useCallback(async (preferId?: string) => {
    try {
      const data = await apiRequest<{ projects: ProjectItem[] }>('/api/v1/projects');
      setProjects(data.projects);
      setActiveProjectIdState((prev) => {
        const stored = typeof window !== 'undefined' ? window.sessionStorage.getItem(STORAGE_KEY) : null;
        const candidate = preferId || prev || stored;
        if (candidate && data.projects.some((p) => p.id === candidate)) {
          if (typeof window !== 'undefined') window.sessionStorage.setItem(STORAGE_KEY, candidate);
          return candidate;
        }
        const first = data.projects[0]?.id ?? null;
        if (first && typeof window !== 'undefined') window.sessionStorage.setItem(STORAGE_KEY, first);
        return first;
      });
    } catch {
      // backend might be booting
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshProjects();
    void refreshAISettings();
  }, [refreshProjects, refreshAISettings]);

  const setActiveProjectId = useCallback((id: string) => {
    // Rule T28: Switching projects MUST cancel any active auto-navigation popup safely!
    setCompletionPopup(null);
    setActiveProjectIdState(id);
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(STORAGE_KEY, id);
    }
  }, []);

  const showCompletionPopup = useCallback((payload: CompletionPopupPayload) => {
    setCompletionPopup(payload);
  }, []);

  const closeCompletionPopup = useCallback(() => {
    setCompletionPopup(null);
  }, []);

  const activeProject = projects.find((p) => p.id === activeProjectId) || null;

  return (
    <ProjectContext.Provider
      value={{
        projects,
        activeProject,
        activeProjectId,
        activeAI,
        loading,
        setActiveProjectId,
        refreshProjects,
        refreshAISettings,
        completionPopup,
        showCompletionPopup,
        closeCompletionPopup,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject phải được dùng bên trong ProjectProvider');
  return ctx;
}
