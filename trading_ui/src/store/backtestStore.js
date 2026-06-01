import { create } from 'zustand';

export const useBacktestStore = create((set) => ({
  jobId: null,
  status: null,    // 'RUNNING' | 'COMPLETE' | 'ERROR'
  progress: 0,
  result: null,
  error: null,
  // multi-segment params
  exchange: 'NSE',
  instrument: 'SPOT',
  walkForward: false,
  customStrategy: {
    enabled: false,
    rsiOversold: 30,
    rsiOverbought: 70,
    emaFast: 9,
    emaSlow: 21,
    atrMultSl: 1.5,
    atrMultTp: 3.0,
    volumeConfirm: true,
  },
  setJobId: (jobId) => set({ jobId }),
  setStatus: (status) => set({ status }),
  setProgress: (progress) => set({ progress }),
  setResult: (result) => set({ result }),
  setError: (error) => set({ error }),
  setExchange: (exchange) => set({ exchange }),
  setInstrument: (instrument) => set({ instrument }),
  setWalkForward: (walkForward) => set({ walkForward }),
  setCustomStrategy: (fields) => set((state) => ({
    customStrategy: { ...state.customStrategy, ...fields },
  })),
  reset: () => set({ jobId: null, status: null, progress: 0, result: null, error: null }),
}));
