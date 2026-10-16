export interface InstagramUser {
  id: number;
  name: string;
  ig_user_id: string | null;
  status: 'pending' | 'connected' | 'needs_reauth';
  token_expires_at: string | null;
  created_at: string;
  has_token: boolean;
}

export interface UniqueLink {
  id: number;
  user: number;
  user_name: string;
  token: string;
  full_link: string;
  video: string;
  status: 'pending' | 'opened' | 'posted' | 'failed';
  expires_at: string | null;
  created_at: string;
}

export interface Post {
  id: number;
  link: number;
  user_name: string;
  ig_media_id: string | null;
  permalink: string | null;
  status: 'queued' | 'publishing' | 'published' | 'failed' | 'deleted';
  posted_at: string | null;
  views: number;
  likes: number;
  comments_count: number;
  last_checked_at: string | null;
  next_check_at: string | null;
  error: string | null;
}

export interface Prize {
  id: number;
  post: number;
  user_name: string;
  milestone: number;
  sent_at: string;
}

export interface DataDeletionRequest {
  id: number;
  confirmation_code: string;
  user_id: string;
  status: 'pending' | 'completed' | 'failed';
  requested_at: string;
  details: string | null;
}

export interface DashboardStats {
  users_by_status: Record<string, number>;
  links_by_status: Record<string, number>;
  posts_by_status: Record<string, number>;
  total_metrics: {
    total_views: number | null;
    total_likes: number | null;
    total_comments: number | null;
  };
  total_prizes: number;
  expiring_tokens_count: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
