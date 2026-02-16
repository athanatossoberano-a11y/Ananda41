import { useState, useEffect, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import { 
  Users, 
  MessageCircle, 
  Ban, 
  Send, 
  Activity, 
  Brain, 
  Eye,
  Search,
  RefreshCw,
  ChevronRight,
  Clock,
  Shield,
  Sparkles,
  Heart,
  HandHeart,
  Star,
  Crown,
  DollarSign,
  TrendingUp,
  CreditCard,
  Package,
  Gift,
  Calendar,
  Filter,
  Download,
  ChevronDown,
  CheckCircle,
  XCircle,
  AlertCircle,
  Wallet
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Stats Card Component
const StatsCard = ({ icon: Icon, title, value, subtitle, color, delay }) => (
  <div 
    data-testid={`stats-card-${title.toLowerCase().replace(/\s+/g, '-')}`}
    className={`bg-white rounded-2xl border border-stone-100 shadow-sm p-6 relative overflow-hidden group hover:border-amber-200/50 transition-all duration-500 hover:-translate-y-1 opacity-0 animate-slide-up stagger-${delay}`}
  >
    <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-amber-50 to-transparent rounded-bl-full opacity-60" />
    <div className="relative z-10">
      <div className={`w-12 h-12 rounded-xl ${color} flex items-center justify-center mb-4`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <p className="text-sm text-stone-400 tracking-wide uppercase font-medium">{title}</p>
      <p className="text-4xl font-light text-stone-800 mt-1" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
        {value}
      </p>
      {subtitle && <p className="text-sm text-stone-500 mt-2">{subtitle}</p>}
    </div>
  </div>
);

// User Card Component
const UserCard = ({ user, onBan }) => {
  const isOnline = user.last_seen && new Date(user.last_seen) > new Date(Date.now() - 15 * 60 * 1000);
  
  return (
    <div 
      data-testid={`user-card-${user.telegram_id}`}
      className="bg-white rounded-xl border border-stone-100 p-4 hover:shadow-md transition-all duration-300 hover:border-amber-200/50"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-100 to-amber-50 flex items-center justify-center">
              <span className="text-amber-700 font-medium">
                {user.name?.charAt(0)?.toUpperCase() || '?'}
              </span>
            </div>
            {isOnline && (
              <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-green-500 rounded-full border-2 border-white" />
            )}
          </div>
          <div>
            <p className="font-medium text-stone-800">{user.name || 'Usuário'}</p>
            <p className="text-sm text-stone-400">
              {user.username ? `@${user.username}` : `ID: ${user.telegram_id}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {user.is_banned ? (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-red-50 text-red-600">
              Banido
            </span>
          ) : (
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-green-50 text-green-600">
              Ativo
            </span>
          )}
          <button
            data-testid={`ban-btn-${user.telegram_id}`}
            onClick={() => onBan(user.telegram_id, !user.is_banned)}
            className={`p-2 rounded-lg transition-all duration-300 ${
              user.is_banned 
                ? 'bg-green-50 text-green-600 hover:bg-green-100' 
                : 'bg-red-50 text-red-600 hover:bg-red-100'
            }`}
            title={user.is_banned ? 'Desbanir' : 'Banir'}
          >
            {user.is_banned ? <Shield className="w-4 h-4" /> : <Ban className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
};

// Message Card Component
const MessageCard = ({ message }) => (
  <div 
    data-testid={`message-card-${message.id}`}
    className="bg-white rounded-xl border border-stone-100 p-4 hover:shadow-sm transition-all duration-300"
  >
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-100 to-amber-50 flex items-center justify-center flex-shrink-0">
        <span className="text-amber-700 text-sm font-medium">
          {message.user_name?.charAt(0)?.toUpperCase() || '?'}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <p className="font-medium text-stone-800 truncate">{message.user_name}</p>
          <p className="text-xs text-stone-400 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {new Date(message.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <div className="space-y-2">
          <div className="bg-stone-50 rounded-lg p-3">
            <p className="text-sm text-stone-600">{message.text}</p>
          </div>
          <div className="bg-gradient-to-r from-amber-50 to-transparent rounded-lg p-3 border-l-2 border-amber-400">
            <p className="text-sm text-stone-700">{message.response}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
);

// Learning Card Component
const LearningCard = ({ learning }) => (
  <div 
    data-testid={`learning-card-${learning.user_id}`}
    className="bg-white rounded-xl border border-stone-100 p-4 hover:shadow-sm transition-all duration-300"
  >
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-100 to-purple-50 flex items-center justify-center flex-shrink-0">
        <Brain className="w-4 h-4 text-purple-600" />
      </div>
      <div className="flex-1">
        <p className="text-xs text-stone-400 mb-1">Usuário: {learning.user_id}</p>
        <p className="text-sm text-stone-700">{learning.learning_text}</p>
        {learning.updated_at && (
          <p className="text-xs text-stone-400 mt-2">
            Atualizado: {new Date(learning.updated_at).toLocaleDateString('pt-BR')}
          </p>
        )}
      </div>
    </div>
  </div>
);

// Prayer Request Card Component
const PrayerCard = ({ request }) => (
  <div 
    data-testid={`prayer-card-${request.id}`}
    className="bg-white rounded-xl border border-stone-100 p-4 hover:shadow-sm transition-all duration-300"
  >
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-rose-100 to-rose-50 flex items-center justify-center flex-shrink-0">
        <Heart className="w-4 h-4 text-rose-500" />
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <p className="text-sm font-medium text-stone-700">{request.user_name}</p>
          <span className={`px-2 py-0.5 rounded-full text-xs ${
            request.status === 'pending' ? 'bg-amber-50 text-amber-600' : 'bg-green-50 text-green-600'
          }`}>
            {request.status === 'pending' ? 'Pendente' : 'Orado'}
          </span>
        </div>
        <p className="text-sm text-stone-600 italic">"{request.request}"</p>
        <p className="text-xs text-stone-400 mt-2">
          {new Date(request.created_at).toLocaleDateString('pt-BR')}
        </p>
      </div>
    </div>
  </div>
);

// Sales Stats Card Component
const SalesStatsCard = ({ icon: Icon, title, value, subtitle, color, trend }) => (
  <div 
    data-testid={`sales-stats-${title.toLowerCase().replace(/\s+/g, '-')}`}
    className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6 relative overflow-hidden group hover:border-emerald-200/50 transition-all duration-500 hover:-translate-y-1"
  >
    <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-emerald-50 to-transparent rounded-bl-full opacity-60" />
    <div className="relative z-10">
      <div className={`w-12 h-12 rounded-xl ${color} flex items-center justify-center mb-4`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <p className="text-sm text-stone-400 tracking-wide uppercase font-medium">{title}</p>
      <p className="text-3xl font-semibold text-stone-800 mt-1">
        {value}
      </p>
      <div className="flex items-center justify-between mt-2">
        {subtitle && <p className="text-sm text-stone-500">{subtitle}</p>}
        {trend && (
          <span className={`text-xs px-2 py-1 rounded-full flex items-center gap-1 ${
            trend > 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'
          }`}>
            <TrendingUp className={`w-3 h-3 ${trend < 0 ? 'rotate-180' : ''}`} />
            {Math.abs(trend)}%
          </span>
        )}
      </div>
    </div>
  </div>
);

// Payment Card Component
const PaymentCard = ({ payment }) => {
  const statusConfig = {
    approved: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-50', label: 'Aprovado' },
    pending: { icon: AlertCircle, color: 'text-amber-500', bg: 'bg-amber-50', label: 'Pendente' },
    rejected: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-50', label: 'Rejeitado' },
    failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-50', label: 'Falhou' }
  };
  
  const status = statusConfig[payment.status] || statusConfig.pending;
  const StatusIcon = status.icon;
  
  const productLabels = {
    premium: { icon: Star, label: 'Premium', color: 'text-yellow-600' },
    vip: { icon: Crown, label: 'VIP', color: 'text-purple-600' },
    meditacao: { icon: Sparkles, label: 'Meditação', color: 'text-blue-600' },
    pacote_meditacao: { icon: Package, label: 'Pacote 10 Med.', color: 'text-indigo-600' },
    oracao: { icon: Heart, label: 'Oração', color: 'text-rose-600' },
    doacao: { icon: Gift, label: 'Doação', color: 'text-pink-600' }
  };
  
  const product = productLabels[payment.product || payment.plan] || { icon: CreditCard, label: payment.product || payment.plan || 'N/A', color: 'text-stone-600' };
  const ProductIcon = product.icon;
  
  return (
    <div 
      data-testid={`payment-card-${payment.id}`}
      className="bg-white rounded-xl border border-stone-100 p-4 hover:shadow-md transition-all duration-300 hover:border-emerald-200/50"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full ${status.bg} flex items-center justify-center`}>
            <StatusIcon className={`w-5 h-5 ${status.color}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <ProductIcon className={`w-4 h-4 ${product.color}`} />
              <p className="font-medium text-stone-800">{product.label}</p>
            </div>
            <p className="text-sm text-stone-400">
              ID: {payment.telegram_id?.slice(0, 8)}...
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="font-semibold text-stone-800">
            R$ {payment.amount?.toFixed(2) || '0.00'}
          </p>
          <p className="text-xs text-stone-400 flex items-center gap-1 justify-end">
            <Clock className="w-3 h-3" />
            {payment.created_at ? new Date(payment.created_at).toLocaleDateString('pt-BR') : 'N/A'}
          </p>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-stone-100 flex items-center justify-between">
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${status.bg} ${status.color}`}>
          {status.label}
        </span>
        {payment.payment_method && (
          <span className="text-xs text-stone-400 flex items-center gap-1">
            <CreditCard className="w-3 h-3" />
            {payment.payment_method === 'pix' ? 'PIX' : 'Checkout'}
          </span>
        )}
      </div>
    </div>
  );
};

// Simple Line Chart Component (CSS-based)
const SimpleLineChart = ({ data, label }) => {
  if (!data || data.length === 0) return null;
  
  const maxValue = Math.max(...data.map(d => d.value), 1);
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * 100;
    const y = 100 - (d.value / maxValue) * 100;
    return `${x},${y}`;
  }).join(' ');
  
  return (
    <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
      <h3 className="text-lg font-medium text-stone-800 mb-4" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
        {label}
      </h3>
      <div className="relative h-48">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
          <defs>
            <linearGradient id="chartGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
            </linearGradient>
          </defs>
          <polygon
            points={`0,100 ${points} 100,100`}
            fill="url(#chartGradient)"
          />
          <polyline
            points={points}
            fill="none"
            stroke="#10b981"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          {data.map((d, i) => {
            const x = (i / (data.length - 1)) * 100;
            const y = 100 - (d.value / maxValue) * 100;
            return (
              <circle
                key={i}
                cx={x}
                cy={y}
                r="3"
                fill="#10b981"
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-xs text-stone-400 mt-2">
          {data.map((d, i) => (
            <span key={i}>{d.label}</span>
          ))}
        </div>
      </div>
    </div>
  );
};

// Top Buyers Component
const TopBuyerCard = ({ buyer, index }) => (
  <div className="flex items-center gap-3 p-3 rounded-xl hover:bg-stone-50 transition-all">
    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
      index === 0 ? 'bg-yellow-100 text-yellow-700' :
      index === 1 ? 'bg-stone-200 text-stone-600' :
      index === 2 ? 'bg-amber-100 text-amber-700' :
      'bg-stone-100 text-stone-500'
    }`}>
      {index + 1}
    </div>
    <div className="flex-1">
      <p className="font-medium text-stone-700 text-sm">ID: {buyer.telegram_id?.slice(0, 10)}...</p>
      <p className="text-xs text-stone-400">{buyer.count} compras</p>
    </div>
    <p className="font-semibold text-emerald-600">R$ {buyer.total?.toFixed(2)}</p>
  </div>
);

// Main App
function App() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [messages, setMessages] = useState([]);
  const [learnings, setLearnings] = useState([]);
  const [prayerRequests, setPrayerRequests] = useState([]);
  const [payments, setPayments] = useState([]);
  const [salesStats, setSalesStats] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [broadcastStatus, setBroadcastStatus] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, usersRes, messagesRes, learningsRes, prayersRes, paymentsRes] = await Promise.all([
        axios.get(`${API}/stats`),
        axios.get(`${API}/users`),
        axios.get(`${API}/messages?limit=50`),
        axios.get(`${API}/learnings`),
        axios.get(`${API}/prayer-requests`),
        axios.get(`${API}/mercadopago/payments`).catch(() => ({ data: { payments: [] } }))
      ]);
      
      setStats(statsRes.data);
      setUsers(usersRes.data.users || []);
      setMessages(messagesRes.data.messages || []);
      setLearnings(learningsRes.data.learnings || []);
      setPrayerRequests(prayersRes.data.requests || []);
      setPayments(paymentsRes.data.payments || []);
      
      // Calculate sales stats
      const allPayments = paymentsRes.data.payments || [];
      const approvedPayments = allPayments.filter(p => p.status === 'approved');
      const totalRevenue = approvedPayments.reduce((sum, p) => sum + (p.amount || 0), 0);
      
      // Today's revenue
      const today = new Date().toISOString().slice(0, 10);
      const todayPayments = approvedPayments.filter(p => p.created_at?.startsWith(today));
      const todayRevenue = todayPayments.reduce((sum, p) => sum + (p.amount || 0), 0);
      
      // This week's revenue
      const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
      const weekPayments = approvedPayments.filter(p => p.created_at >= weekAgo);
      const weekRevenue = weekPayments.reduce((sum, p) => sum + (p.amount || 0), 0);
      
      // This month's revenue
      const monthStart = new Date().toISOString().slice(0, 7);
      const monthPayments = approvedPayments.filter(p => p.created_at?.startsWith(monthStart));
      const monthRevenue = monthPayments.reduce((sum, p) => sum + (p.amount || 0), 0);
      
      // Products breakdown
      const productBreakdown = {};
      approvedPayments.forEach(p => {
        const product = p.product || p.plan || 'other';
        if (!productBreakdown[product]) {
          productBreakdown[product] = { count: 0, total: 0 };
        }
        productBreakdown[product].count++;
        productBreakdown[product].total += p.amount || 0;
      });
      
      // Top buyers
      const buyerStats = {};
      approvedPayments.forEach(p => {
        const id = p.telegram_id;
        if (!buyerStats[id]) {
          buyerStats[id] = { telegram_id: id, count: 0, total: 0 };
        }
        buyerStats[id].count++;
        buyerStats[id].total += p.amount || 0;
      });
      const topBuyers = Object.values(buyerStats)
        .sort((a, b) => b.total - a.total)
        .slice(0, 5);
      
      // Daily revenue for chart (last 7 days)
      const dailyRevenue = [];
      for (let i = 6; i >= 0; i--) {
        const date = new Date(Date.now() - i * 24 * 60 * 60 * 1000);
        const dateStr = date.toISOString().slice(0, 10);
        const dayPayments = approvedPayments.filter(p => p.created_at?.startsWith(dateStr));
        const dayTotal = dayPayments.reduce((sum, p) => sum + (p.amount || 0), 0);
        dailyRevenue.push({
          label: date.toLocaleDateString('pt-BR', { weekday: 'short' }),
          value: dayTotal
        });
      }
      
      setSalesStats({
        totalRevenue,
        todayRevenue,
        weekRevenue,
        monthRevenue,
        totalTransactions: approvedPayments.length,
        pendingTransactions: allPayments.filter(p => p.status === 'pending').length,
        productBreakdown,
        topBuyers,
        dailyRevenue
      });
      
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleBan = async (telegramId, isBanned) => {
    try {
      await axios.post(`${API}/users/ban`, { telegram_id: telegramId, is_banned: isBanned });
      fetchData();
    } catch (error) {
      console.error('Error banning user:', error);
    }
  };

  const handleBroadcast = async () => {
    if (!broadcastMessage.trim()) return;
    
    try {
      setBroadcastStatus('sending');
      const response = await axios.post(`${API}/broadcast`, { message: broadcastMessage });
      setBroadcastStatus(`Enviado para ${response.data.sent_to} usuários!`);
      setBroadcastMessage('');
      setTimeout(() => setBroadcastStatus(null), 3000);
    } catch (error) {
      console.error('Error broadcasting:', error);
      setBroadcastStatus('Erro ao enviar');
      setTimeout(() => setBroadcastStatus(null), 3000);
    }
  };

  const filteredUsers = users.filter(user => 
    user.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    user.username?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    user.telegram_id?.includes(searchQuery)
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAFAF9] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-amber-200 to-amber-100 flex items-center justify-center animate-pulse-soft">
            <Sparkles className="w-8 h-8 text-amber-600" />
          </div>
          <p className="text-stone-500">Carregando...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAF9] bg-noise">
      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-stone-200/50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-amber-500 flex items-center justify-center shadow-md">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 
                  data-testid="app-title"
                  className="text-2xl font-light text-stone-800" 
                  style={{ fontFamily: 'Cormorant Garamond, serif' }}
                >
                  Ananda
                </h1>
                <p className="text-xs text-stone-400 tracking-wide">Dashboard Espiritual</p>
              </div>
            </div>
            <button
              data-testid="refresh-btn"
              onClick={fetchData}
              className="p-2 rounded-xl bg-stone-100 hover:bg-stone-200 transition-colors duration-300"
            >
              <RefreshCw className="w-5 h-5 text-stone-600" />
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="border-b border-stone-200/50 bg-white/50">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1 overflow-x-auto">
            {[
              { id: 'dashboard', label: 'Dashboard', icon: Activity },
              { id: 'sales', label: 'Vendas', icon: DollarSign },
              { id: 'users', label: 'Usuários', icon: Users },
              { id: 'messages', label: 'Mensagens', icon: MessageCircle },
              { id: 'prayers', label: 'Pedidos', icon: HandHeart },
              { id: 'learnings', label: 'Aprendizados', icon: Brain },
              { id: 'broadcast', label: 'Broadcast', icon: Send }
            ].map(tab => (
              <button
                key={tab.id}
                data-testid={`tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-all duration-300 ${
                  activeTab === tab.id
                    ? 'border-amber-500 text-amber-700 bg-amber-50/50'
                    : 'border-transparent text-stone-500 hover:text-stone-700 hover:bg-stone-50'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                <span className="text-sm font-medium whitespace-nowrap">{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="space-y-8">
            <div>
              <h2 
                className="text-3xl font-light text-stone-800 mb-2" 
                style={{ fontFamily: 'Cormorant Garamond, serif' }}
              >
                Visão Geral
              </h2>
              <p className="text-stone-500">Acompanhe as métricas do seu bot espiritual</p>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
              <StatsCard
                icon={Users}
                title="Total de Almas"
                value={stats?.total_users || 0}
                subtitle="Usuários registrados"
                color="bg-gradient-to-br from-amber-400 to-amber-500"
                delay={1}
              />
              <StatsCard
                icon={Activity}
                title="Almas Ativas"
                value={stats?.active_users || 0}
                subtitle="Últimos 15 minutos"
                color="bg-gradient-to-br from-green-400 to-green-500"
                delay={2}
              />
              <StatsCard
                icon={MessageCircle}
                title="Mensagens"
                value={stats?.total_messages || 0}
                subtitle={`${stats?.messages_today || 0} hoje`}
                color="bg-gradient-to-br from-blue-400 to-blue-500"
                delay={3}
              />
              <StatsCard
                icon={Heart}
                title="Pedidos de Oração"
                value={stats?.prayer_requests || 0}
                subtitle="Intenções recebidas"
                color="bg-gradient-to-br from-rose-400 to-rose-500"
                delay={4}
              />
              <StatsCard
                icon={Star}
                title="Premium"
                value={stats?.premium_users || 0}
                subtitle="Assinantes Premium"
                color="bg-gradient-to-br from-yellow-400 to-yellow-500"
                delay={5}
              />
              <StatsCard
                icon={Crown}
                title="VIP"
                value={stats?.vip_users || 0}
                subtitle="Assinantes VIP"
                color="bg-gradient-to-br from-purple-400 to-purple-500"
                delay={6}
              />
            </div>

            {/* Recent Activity */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-medium text-stone-800" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
                    Mensagens Recentes
                  </h3>
                  <button
                    data-testid="view-all-messages"
                    onClick={() => setActiveTab('messages')}
                    className="text-sm text-amber-600 hover:text-amber-700 flex items-center gap-1"
                  >
                    Ver todas <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
                <div className="space-y-3 max-h-80 overflow-y-auto">
                  {messages.slice(0, 5).map(msg => (
                    <MessageCard key={msg.id} message={msg} />
                  ))}
                  {messages.length === 0 && (
                    <p className="text-center text-stone-400 py-8">Nenhuma mensagem ainda</p>
                  )}
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-medium text-stone-800" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
                    Aprendizados da IA
                  </h3>
                  <button
                    data-testid="view-all-learnings"
                    onClick={() => setActiveTab('learnings')}
                    className="text-sm text-amber-600 hover:text-amber-700 flex items-center gap-1"
                  >
                    Ver todos <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
                <div className="space-y-3 max-h-80 overflow-y-auto">
                  {learnings.slice(0, 5).map(learning => (
                    <LearningCard key={learning.user_id} learning={learning} />
                  ))}
                  {learnings.length === 0 && (
                    <p className="text-center text-stone-400 py-8">Nenhum aprendizado registrado</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 
                  className="text-3xl font-light text-stone-800 mb-2" 
                  style={{ fontFamily: 'Cormorant Garamond, serif' }}
                >
                  Usuários
                </h2>
                <p className="text-stone-500">Gerencie as almas conectadas com Ananda</p>
              </div>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                <input
                  data-testid="search-users"
                  type="text"
                  placeholder="Buscar usuário..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-4 py-2 rounded-xl border border-stone-200 focus:border-amber-400 focus:ring-2 focus:ring-amber-100 outline-none transition-all duration-300 text-sm"
                />
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredUsers.map(user => (
                <UserCard key={user.telegram_id} user={user} onBan={handleBan} />
              ))}
              {filteredUsers.length === 0 && (
                <div className="col-span-full text-center py-12 text-stone-400">
                  <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Nenhum usuário encontrado</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Messages Tab */}
        {activeTab === 'messages' && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Eye className="w-6 h-6 text-amber-500" />
              <div>
                <h2 
                  className="text-3xl font-light text-stone-800" 
                  style={{ fontFamily: 'Cormorant Garamond, serif' }}
                >
                  Monitoramento
                </h2>
                <p className="text-stone-500">Acompanhe as conversas em tempo real</p>
              </div>
            </div>
            
            <div className="space-y-4 max-h-[calc(100vh-300px)] overflow-y-auto pr-2">
              {messages.map(msg => (
                <MessageCard key={msg.id} message={msg} />
              ))}
              {messages.length === 0 && (
                <div className="text-center py-12 text-stone-400">
                  <MessageCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Nenhuma mensagem registrada</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Prayer Requests Tab */}
        {activeTab === 'prayers' && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <HandHeart className="w-6 h-6 text-rose-500" />
              <div>
                <h2 
                  className="text-3xl font-light text-stone-800" 
                  style={{ fontFamily: 'Cormorant Garamond, serif' }}
                >
                  Pedidos de Oração
                </h2>
                <p className="text-stone-500">Intenções enviadas pelas almas</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {prayerRequests.map(request => (
                <PrayerCard key={request.id} request={request} />
              ))}
              {prayerRequests.length === 0 && (
                <div className="col-span-full text-center py-12 text-stone-400">
                  <Heart className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Nenhum pedido de oração ainda</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Learnings Tab */}
        {activeTab === 'learnings' && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Brain className="w-6 h-6 text-purple-500" />
              <div>
                <h2 
                  className="text-3xl font-light text-stone-800" 
                  style={{ fontFamily: 'Cormorant Garamond, serif' }}
                >
                  Aprendizados da IA
                </h2>
                <p className="text-stone-500">O que Ananda aprendeu sobre cada alma</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {learnings.map(learning => (
                <LearningCard key={learning.user_id} learning={learning} />
              ))}
              {learnings.length === 0 && (
                <div className="col-span-full text-center py-12 text-stone-400">
                  <Brain className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Nenhum aprendizado registrado ainda</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Broadcast Tab */}
        {activeTab === 'broadcast' && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Send className="w-6 h-6 text-amber-500" />
              <div>
                <h2 
                  className="text-3xl font-light text-stone-800" 
                  style={{ fontFamily: 'Cormorant Garamond, serif' }}
                >
                  Broadcast
                </h2>
                <p className="text-stone-500">Envie uma mensagem para todas as almas</p>
              </div>
            </div>
            
            <div className="bg-white rounded-2xl border border-stone-100 shadow-sm p-6 max-w-2xl">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-stone-700 mb-2">
                    Mensagem Espiritual
                  </label>
                  <textarea
                    data-testid="broadcast-textarea"
                    value={broadcastMessage}
                    onChange={(e) => setBroadcastMessage(e.target.value)}
                    placeholder="Escreva uma mensagem de luz para todas as almas..."
                    className="w-full h-40 px-4 py-3 rounded-xl border border-stone-200 focus:border-amber-400 focus:ring-2 focus:ring-amber-100 outline-none transition-all duration-300 resize-none"
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <p className="text-sm text-stone-400">
                    Será enviado para {users.filter(u => !u.is_banned).length} usuários ativos
                  </p>
                  <button
                    data-testid="send-broadcast-btn"
                    onClick={handleBroadcast}
                    disabled={!broadcastMessage.trim() || broadcastStatus === 'sending'}
                    className="bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-500 hover:to-amber-600 text-white rounded-full px-8 py-3 transition-all duration-300 shadow-md hover:shadow-lg hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    <Send className="w-4 h-4" />
                    {broadcastStatus === 'sending' ? 'Enviando...' : 'Enviar Broadcast'}
                  </button>
                </div>
                
                {broadcastStatus && broadcastStatus !== 'sending' && (
                  <div className={`p-3 rounded-xl text-sm ${
                    broadcastStatus.includes('Erro') 
                      ? 'bg-red-50 text-red-700' 
                      : 'bg-green-50 text-green-700'
                  }`}>
                    {broadcastStatus}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-stone-200/50 bg-white/30 mt-auto">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <p className="text-center text-sm text-stone-400">
            Ananda - Guia Espiritual sob a luz de Abba
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
