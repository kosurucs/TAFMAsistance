import { create } from 'zustand';

export const useBacktestStore = create((set) => ({
  jobId: null,
  status: null,    // 'RUNNING' | 'COMPLETE' | 'ERROR'
  progress: 0,
  result: null,
  error: null,
  setJobId: (jobId) => set({ jobId }),
  setStatus: (status) => set({ status }),
  setProgress: (progress) => set({ progress }),
  setResult: (result) => set({ result }),
  setError: (error) => set({ error }),
  reset: () => set({ jobId: null, status: null, progress: 0, result: null, error: null }),
}));
