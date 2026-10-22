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
  video_url?: string;
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
  deleted_detected_at?: string | null;
  views: number;
  likes: number;
  comments_count: number;
  last_checked_at: string | null;
  next_check_at: string | null;
  error: string | null;
  retry_count?: number;
}

export interface PostStat {
  id: number;
  checked_at: string;
  views: number;
  likes: number;
  comments_count: number;
}

export interface Prize {
  id: number;
  post: number;
  user_name: string;
  milestone: number;
  sent_at: string;
}

export interface Notification {
  id: number;
  user: number;
  kind: 'prize' | 'system';
  message: string;
  is_read: boolean;
  created_at: string;
  related_prize: number | null;
}

export interface DataDeletionRequest {
  id: number;
  confirmation_code: string;
  user_id: string;
  status: 'pending' | 'completed' | 'failed';
  requested_at: string;
  details: string | null;
}

export interface InstagramErrorsSummary {
  media_not_found: number;
  token_invalid: number;
  permission_denied: number;
  rate_limit: number;
  server_error: number;
  other: number;
  total: number;
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
  instagram_errors_last_hour?: InstagramErrorsSummary;
  dry_run?: boolean;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  role: 'admin' | 'user';
  is_staff: boolean;
  instagram_user?: InstagramUser | null;
  dry_run?: boolean;
}

export interface UserSummary {
  total_views: number;
  total_likes: number;
  total_comments: number;
  posts_count: number;
  prizes_count: number;
  last_checked_at: string | null;
  next_milestone?: number | null;
  views_remaining?: number | null;
  progress_percent?: number;
  milestones?: number[];
}

export interface AdminSummary {
  total_users: number;
  connected_users: number;
  needs_reauth_users: number;
  posts_by_status: Record<string, number>;
  total_metrics: {
    total_views: number;
    total_likes: number;
    total_comments: number;
  };
  total_views: number;
  total_likes: number;
  total_comments: number;
  total_prizes: number;
  expiring_tokens_count: number;
  instagram_errors_last_hour?: InstagramErrorsSummary;
  dry_run?: boolean;
}

export interface AdminUserItem {
  id: number;
  username: string;
  name: string;
  ig_user_id: string | null;
  status: 'pending' | 'connected' | 'needs_reauth';
  posts_count: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  last_posted_at: string | null;
  created_at: string;
  has_token: boolean;
}

export interface AdminDailyStat {
  date: string;
  new_posts: number;
  total_views: number;
  total_likes: number;
}

export interface VideoItem {
  id: number;
  title: string;
  file: string;
  video_url: string;
  is_default: boolean;
  owner: number | null;
  owner_name: string | null;
  is_active: boolean;
  status: 'pending' | 'processing' | 'ready' | 'failed';
  processing_error?: string | null;
  created_at: string;
}

export interface CampaignPost {
  id: number;
  thumbnail_url: string | null;
  permalink: string | null;
  status: 'verified' | 'rejected' | 'revoked' | 'queued' | 'publishing' | 'published' | 'deleted' | 'failed';
  source: 'site' | 'self';
  views: number;
  likes: number;
  comments_count: number;
  posted_at: string | null;
  last_synced_at: string | null;
  username: string;
  code: string;
}

export interface PublishStatus {
  has_post: boolean;
  post_id?: number;
  status: 'queued' | 'publishing' | 'published' | 'failed' | 'none' | 'deleted';
  posted_at?: string | null;
  views?: number;
  likes?: number;
  comments_count?: number;
  permalink?: string | null;
  error?: string | null;
  retry_count?: number;
  can_retry?: boolean;
  retries_left?: number;
  can_publish?: boolean;
  can_publish_reason?: string | null;
  code?: string | null;
  upload_limits?: {
    max_size_mb: number;
    allowed_types: string[];
  };
}
