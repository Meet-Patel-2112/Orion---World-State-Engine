// Creator profile, preferences and password (backend: routes/auth.py, services/profile_service.py).
import { apiFetch } from './client';

export interface Preferences {
  /** How much a character says per reply in character chat */
  chat_reply_length: 'short' | 'medium' | 'long';
  /** Re-extraction review: start new items ticked */
  review_preselect_new: boolean;
}

export interface Profile {
  id: string;
  email: string;
  created_at: string;
  display_name: string;
  preferences: Preferences;
  stats: { worlds: number; manuscripts: number; chapters: number; entities: number };
}

export const getProfile = () => apiFetch<Profile>('/auth/profile');

export const updateProfile = (body: { display_name?: string; preferences?: Partial<Preferences> }) =>
  apiFetch<Profile>('/auth/profile', { method: 'PUT', body: JSON.stringify(body) });

export const changePassword = (current_password: string, new_password: string) =>
  apiFetch<{ message: string }>('/auth/password', {
    method: 'POST',
    body: JSON.stringify({ current_password, new_password }),
  });

export const updateWorld = (worldId: string, body: { name?: string; description?: string }) =>
  apiFetch<{ id: string; name: string; description: string }>(`/worlds/${worldId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });

export const deleteWorld = (worldId: string) => apiFetch<void>(`/worlds/${worldId}`, { method: 'DELETE' });

export const getWorld = (worldId: string) =>
  apiFetch<{ id: string; name: string; description: string }>(`/worlds/${worldId}`);
