import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: API_URL,
});

// Add a request interceptor to include the JWT token in headers
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const authApi = {
  signup: (userData: any) => api.post('/signup', userData),
  login: (credentials: any) => api.post('/login', credentials),
  logout: () => api.post('/logout'),
};

export const chatApi = {
  ask: (question: string, conversation_id?: number) => api.post('/ask', { question, conversation_id }),
  getHistory: () => api.get('/history'),
  clearHistory: () => api.delete('/history'),
  deleteConversation: (id: number) => api.delete(`/conversations/${id}`),
  getConversationMessages: (id: number) => api.get(`/conversations/${id}`),
};

export default api;
