const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export type NumberItem = { id: number; number: number; status: string }
export type AdminNumberItem = NumberItem & { buyer_name:string; buyer_email:string; buyer_phone:string; reservation_code:string|null; reservation_status:string|null; updated_at:string }
export type Raffle = {
  id: number; title: string; slug: string; description: string; terms: string; accent_color: string; prize: string; prizes: string[];
  cover_url: string | null;
  total_numbers: number; number_price: number; fundraising_goal: number | null; draw_date: string | null; status: string;
  bank_name: string; account_type: string; account_number: string; account_holder: string;
  account_holder_id: string; transfer_email: string; phone_required: boolean; mercadopago_enabled: boolean; raffle_pro_active:boolean;
  available_count: number; reserved_count: number; sold_count: number; sold_revenue: number;
  winning_number: number | null; winners: {position:number;prize:string;number:number;buyer_name:string}[]; drawn_at: string | null;
  owner: { id: number; username: string; email: string }; numbers: NumberItem[];
}

export type Reservation = {
  code: string; raffle_title: string; raffle_slug: string; buyer_name: string;
  buyer_email: string; buyer_phone: string; status: string; source: 'online'|'manual'; expires_at: string; numbers: number[]; total: number;
  receipt_url: string | null; receipt_uploaded_at: string | null;
}

export type BuyerReservation = {
  code:string; raffle_title:string; raffle_slug:string; buyer_name:string; buyer_email:string; buyer_phone:string;
  status:string; source:'online'|'manual'; expires_at:string; numbers:number[]; number_price:number; total:number;
  bank_name:string; account_type:string; account_number:string; account_holder:string;
  account_holder_id:string; transfer_email:string; mercadopago_enabled:boolean; receipt_uploaded:boolean;
  receipt_uploaded_at:string|null;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token')
  const isFormData = options.body instanceof FormData
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...(!isFormData ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Token ${token}` } : {}), ...options.headers },
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || Object.values(data).flat().join(' ') || 'Ocurrió un error')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export async function apiFile(path: string): Promise<Blob> {
  const token = localStorage.getItem('token')
  const normalizedPath = path.startsWith('/api/') ? path.slice(4) : path
  const response = await fetch(`${API_URL}${normalizedPath}`, {
    headers: token ? { Authorization: `Token ${token}` } : {},
  })
  if (!response.ok) throw new Error('No se pudo abrir el comprobante.')
  return response.blob()
}
