import { create } from 'zustand';

export const useChatStore = create((set) => ({
  messages: [],
  loading: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
  setLoading: (loading) => set({ loading }),
}));
