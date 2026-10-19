import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import type { UserProfile } from '../types';

interface AuthContextType {
  isAuthenticated: boolean;
  user: UserProfile | null;
  role: 'admin' | 'user' | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<UserProfile>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return !!localStorage.getItem('access_token');
  });
  const [user, setUser] = useState<UserProfile | null>(null);
  const [role, setRole] = useState<'admin' | 'user' | null>(() => {
    return (localStorage.getItem('user_role') as 'admin' | 'user') || null;
  });
  const [loading, setLoading] = useState<boolean>(true);

  const fetchProfile = async () => {
    try {
      const response = await apiClient.get<UserProfile>('/api/me/');
      setUser(response.data);
      const userRole = response.data.role;
      setRole(userRole);
      localStorage.setItem('user_role', userRole);
      return response.data;
    } catch {
      logout();
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (localStorage.getItem('access_token')) {
      fetchProfile();
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (username: string, password: string): Promise<UserProfile> => {
    const response = await apiClient.post('/api/token/', { username, password });
    localStorage.setItem('access_token', response.data.access);
    localStorage.setItem('refresh_token', response.data.refresh);
    if (response.data.role) {
      localStorage.setItem('user_role', response.data.role);
      setRole(response.data.role);
    }
    setIsAuthenticated(true);
    const profile = await fetchProfile();
    if (!profile) {
      throw new Error("Profil ma'lumotlarini yuklab bo'lmadi.");
    }
    return profile;
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_role');
    setIsAuthenticated(false);
    setUser(null);
    setRole(null);
  };

  const refreshProfile = async () => {
    await fetchProfile();
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, user, role, loading, login, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
