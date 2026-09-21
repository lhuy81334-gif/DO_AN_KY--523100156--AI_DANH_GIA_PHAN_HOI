import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 300000,
});

export type Overview = {
  total_products: number;
  total_reviews: number;
  total_reviews_with_images: number;
  total_reviews_need_seller_attention: number;
};

export type SellerFeedbackSummary = {
  total_reviews: number;
  reviews_with_images: number;
  reviews_with_image_analysis: number;
  average_trust_score: number;
  flagged_reviews: number;
  trust_level_counts: Record<string, number>;
};

export type SellerReviewDecision = {
  review_id: number;
  external_review_id: string;
  product_id: number;
  external_product_id: string;
  platform_code: string;
  source: string;
  product_title: string;
  product_url?: string;
  review_source_url?: string;
  rating: number;
  created_at?: string;
  review_text: string;
  image_urls: string[];
  flags: string[];
  negative_aspects: string[];
  positive_aspects: string[];
  image_fit: { label: string; answer: string; score: number; status: string };
  evidence: { label: string; answer: string; content_specificity_score: number; image_evidence_score: number };
  trust: { label: string; answer: string; score: number; level: string };
  seller_action: { label: string; answer: string; priority: string };
};

export type ImageComparison = {
  review_id: number;
  external_review_id: string;
  product_id: number;
  external_product_id: string;
  platform_code: string;
  source: string;
  product_title: string;
  product_url?: string;
  review_source_url?: string;
  rating: number;
  created_at?: string;
  review_text: string;
  image_urls: string[];
  analysis_status: string;
  image_relevance_score: number | null;
  image_evidence_status: string;
  expected_product_labels: string[];
  best_expected_label?: string;
  best_other_label?: string;
  category_status?: string;
  category_margin?: number;
  review_claim_type?: string;
  expected_evidence_labels: string[];
  claim_evidence_score?: number;
  claim_evidence_status?: string;
  best_claim_label?: string;
  best_other_evidence_label?: string;
  images_analyzed: number;
  product_images_used: number;
  text_score?: number;
  product_image_score?: number;
  category_score?: number;
  image_hash?: string;
  flags: string[];
  trust: { label: string; answer: string; score: number; level: string };
};

export type ProductLinkResolution = {
  platform_code: string;
  external_product_id: string;
  spid?: string;
  detected_from: string;
  candidate_product_ids: Record<string, string>;
  product_id?: number;
  product_title?: string;
  product_url: string;
  product_images?: string[];
  images_found?: number;
  has_data: boolean;
  total_reviews: number;
  total_reviews_with_images: number;
  message: string;
};

export type ProductLinkIngestResult = ProductLinkResolution & {
  status?: 'ok' | 'needs_browser_session';
  requires_browser_session?: boolean;
  source_reviews: number;
  normalized_reviews: number;
  source_mode?: string;
  import_stats: {
    total_rows: number;
    inserted: number;
    updated: number;
    duplicated: number;
    failed: number;
  };
  product_metadata?: {
    images_found: number;
    product_images: string[];
    error?: string;
  };
  image_analysis?: {
    image_reviews_analyzed: number;
    image_reviews_failed: number;
    last_error: string;
  };
  analyzed_reviews: number;
};

export type BrowserSession = {
  available: boolean;
  active: boolean;
  opened?: boolean;
  profile_dir: string;
  message: string;
};

export type ProductImageAnalysisResult = {
  product_id: number;
  platform_code: string;
  external_product_id: string;
  product_metadata: {
    images_found: number;
    product_images: string[];
    error?: string;
  };
  total_reviews_with_images: number;
  image_analysis: {
    image_reviews_analyzed: number;
    image_reviews_failed: number;
    last_error: string;
  };
  message: string;
};

export async function getOverview(params?: { platform_code?: string; external_product_id?: string; product_id?: number }) {
  const { data } = await api.get<Overview>('/datasets/overview', { params });
  return data;
}

export async function getSellerFeedbackSummary(params?: { platform_code?: string; external_product_id?: string }) {
  const { data } = await api.get<SellerFeedbackSummary>('/seller-feedback/summary', { params });
  return data;
}

export async function getSellerFeedbackReviews(params?: { platform_code?: string; external_product_id?: string; rating?: number; only_attention?: boolean; limit?: number }) {
  const { data } = await api.get<SellerReviewDecision[]>('/seller-feedback/reviews', { params });
  return data;
}

export async function getImageComparisons(params?: { platform_code?: string; external_product_id?: string; limit?: number }) {
  const { data } = await api.get<ImageComparison[]>('/seller-feedback/image-comparisons', { params });
  return data;
}

export async function resolveProductLink(product_url: string) {
  const { data } = await api.post<ProductLinkResolution>('/seller-feedback/resolve-product-link', { product_url });
  return data;
}

export async function ingestProductLink(
  product_url: string,
  options?: { page_size?: number; max_pages_per_star?: number; delay?: number }
) {
  const { data } = await api.post<ProductLinkIngestResult>('/seller-feedback/ingest-product-link', {
    product_url,
    ...options,
  });
  return data;
}

export async function openTikTokSession(product_url?: string) {
  const { data } = await api.post<BrowserSession>('/seller-feedback/tiktok/session/open', { product_url });
  return data;
}

export async function openLazadaSession(product_url?: string) {
  const { data } = await api.post<BrowserSession>('/seller-feedback/lazada/session/open', { product_url });
  return data;
}

export async function analyzeProductImages(params: {
  product_url?: string;
  platform_code?: string;
  external_product_id?: string;
  product_id?: number;
  limit?: number;
  max_images_per_review?: number;
}) {
  const { data } = await api.post<ProductImageAnalysisResult>('/seller-feedback/analyze-images', params);
  return data;
}

export default api;
