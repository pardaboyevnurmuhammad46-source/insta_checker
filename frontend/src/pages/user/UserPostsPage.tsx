import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { CampaignPost, PaginatedResponse } from '../../types';
import { formatNumber, formatDate, formatTimeAgo } from '../../utils/format';
import { Pagination } from '../../components/Pagination';
import { Eye, Heart, MessageCircle, ExternalLink, Search, Filter, Trash2, Film, RefreshCw } from 'lucide-react';

export const UserPostsPage: React.FC = () => {
  const [posts, setPosts] = useState<CampaignPost[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  
  // Filters
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'published' | 'deleted'>('published');

  const fetchPosts = async () => {
    try {
      setLoading(true);
      // Constructing query string based on filters
      const statusParam = statusFilter !== 'all' ? `&status=${statusFilter}` : '';
      const searchParam = search ? `&search=${search}` : '';
      
      const res = await apiClient.get<PaginatedResponse<CampaignPost>>(
        `/api/user/posts/?page=${page}${statusParam}${searchParam}`
      );
      setPosts(res.data.results || []);
      setTotalCount(res.data.count || 0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  // Debounced fetch for search
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchPosts();
    }, 400);
    return () => clearTimeout(timer);
  }, [search, statusFilter]);

  useEffect(() => {
    fetchPosts();
  }, [page]);

  const handleDeletePost = async (postId: number) => {
    if (!window.confirm("Haqiqatan ham ushbu postni o'chirmoqchimisiz? Tarix tozalanadi.")) return;
    try {
      await apiClient.delete(`/api/user/posts/${postId}/`);
      fetchPosts();
    } catch {}
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Mening Postlarim
          </h1>
          <p className="text-slate-400 text-sm mt-1">Barcha Reels videolaringiz va ko'rsatkichlari</p>
        </div>
        <button onClick={fetchPosts} className="p-2 bg-slate-800 text-slate-300 rounded-lg hover:text-white transition w-fit">
           <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Filters Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex flex-col md:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input 
            type="text" 
            placeholder="Kod yoki izoh bo'yicha qidirish..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:border-indigo-500 outline-none transition"
          />
        </div>
        <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 w-full md:w-auto">
          {['published', 'deleted', 'all'].map(s => (
             <button 
               key={s}
               onClick={() => setStatusFilter(s as any)}
               className={`flex-1 md:px-4 py-1.5 rounded-md text-xs font-semibold capitalize transition ${statusFilter === s ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
             >
               {s === 'published' ? 'Faol' : s === 'deleted' ? "O'chirilgan" : 'Barchasi'}
             </button>
          ))}
        </div>
      </div>

      {/* Mobile Cards / Desktop Grid */}
      {loading && posts.length === 0 ? (
         <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-pulse">
            {[1,2,3].map(i => <div key={i} className="h-40 bg-slate-900 rounded-xl border border-slate-800" />)}
         </div>
      ) : posts.length === 0 ? (
        <div className="py-16 bg-slate-900 border border-slate-800 rounded-2xl text-center">
          <Film size={40} className="mx-auto text-slate-600 mb-3" />
          <p className="text-slate-300 font-medium">Postlar topilmadi</p>
          <p className="text-slate-500 text-sm mt-1">Boshqa filtr tanlab ko'ring yoki yangi video joylang.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {posts.map(post => (
            <div key={post.id} className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden flex flex-col group hover:border-slate-700 transition">
              {/* Card Header & Thumbnail */}
              <div className="h-32 bg-slate-800 relative overflow-hidden">
                {post.thumbnail_url ? (
                  <img src={post.thumbnail_url} alt="Cover" className="w-full h-full object-cover opacity-80 group-hover:scale-105 transition duration-500" />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-slate-600 bg-slate-900/50">
                    <Film size={24} className="mb-1" />
                    <span className="text-[10px] uppercase font-bold tracking-widest">Reels</span>
                  </div>
                )}
                {/* Overlay gradient */}
                <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-900/40 to-transparent"></div>
                
                <div className="absolute top-2 right-2 flex gap-1">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${post.status === 'deleted' ? 'bg-rose-500/80 text-white' : 'bg-emerald-500/80 text-white'}`}>
                    {post.status === 'deleted' ? "O'chirilgan" : 'Faol'}
                  </span>
                </div>
                
                <div className="absolute bottom-2 left-3 right-3 flex justify-between items-end">
                   <span className="font-mono text-amber-400 font-bold bg-slate-950/80 px-2 py-0.5 rounded border border-slate-700 text-xs">
                     {post.code || '#NOCODE'}
                   </span>
                   {post.permalink && (
                     <a href={post.permalink} target="_blank" rel="noreferrer" className="w-7 h-7 bg-white/10 hover:bg-white/20 backdrop-blur rounded-full flex items-center justify-center text-white transition">
                       <ExternalLink size={12} />
                     </a>
                   )}
                </div>
              </div>

              {/* Card Body - Stats */}
              <div className="p-4 flex-1 flex flex-col justify-between space-y-4">
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-slate-950 rounded-lg p-2 text-center border border-slate-800">
                     <Eye size={14} className="mx-auto text-sky-400 mb-1" />
                     <span className="block text-white font-bold text-sm">{formatNumber(post.views)}</span>
                  </div>
                  <div className="bg-slate-950 rounded-lg p-2 text-center border border-slate-800">
                     <Heart size={14} className="mx-auto text-rose-400 mb-1" />
                     <span className="block text-slate-300 font-bold text-sm">{formatNumber(post.likes)}</span>
                  </div>
                  <div className="bg-slate-950 rounded-lg p-2 text-center border border-slate-800">
                     <MessageCircle size={14} className="mx-auto text-emerald-400 mb-1" />
                     <span className="block text-slate-300 font-bold text-sm">{formatNumber(post.comments_count)}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] pt-3 border-t border-slate-800">
                  <span className="text-slate-500">{formatDate(post.posted_at)}</span>
                  <button onClick={() => handleDeletePost(post.id)} className="text-slate-500 hover:text-rose-400 flex items-center gap-1 transition">
                    <Trash2 size={12} /> O'chirish
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {totalCount > posts.length && (
        <Pagination currentPage={page} totalCount={totalCount} onPageChange={(p) => setPage(p)} />
      )}
    </div>
  );
};
