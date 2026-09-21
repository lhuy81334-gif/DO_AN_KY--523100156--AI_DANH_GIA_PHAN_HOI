import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, BarChart3, Camera, ExternalLink, KeyRound, Loader2, MessageSquareText, PackageSearch, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import {
  analyzeProductImages,
  getImageComparisons,
  getOverview,
  getSellerFeedbackReviews,
  getSellerFeedbackSummary,
  ingestProductLink,
  openLazadaSession,
  openTikTokSession,
  resolveProductLink,
  ImageComparison,
  Overview,
  SellerFeedbackSummary,
  SellerReviewDecision,
} from './api/client';

function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [feedbackSummary, setFeedbackSummary] = useState<SellerFeedbackSummary | null>(null);
  const [attentionReviews, setAttentionReviews] = useState<SellerReviewDecision[]>([]);
  const [imageComparisons, setImageComparisons] = useState<ImageComparison[]>([]);
  const [feedbackFilter, setFeedbackFilter] = useState({ platform_code: 'lazada', external_product_id: '310626559' });
  const [attentionRating, setAttentionRating] = useState(0);
  const [productImages, setProductImages] = useState<string[]>([]);
  const [productLink, setProductLink] = useState('');
  const [linkStatus, setLinkStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [resolvingLink, setResolvingLink] = useState(false);
  const [ingestingLink, setIngestingLink] = useState(false);
  const [analyzingImages, setAnalyzingImages] = useState(false);
  const [openingBrowserSession, setOpeningBrowserSession] = useState(false);
  const [error, setError] = useState('');
  const [jobStep, setJobStep] = useState('');
  const loadRequestId = useRef(0);

  useEffect(() => {
    loadSellerFeedback();
  }, []);

  function clearFeedbackData() {
    setFeedbackSummary(null);
    setAttentionReviews([]);
    setImageComparisons([]);
    setOverview(null);
  }

  async function loadSellerFeedback(nextFilter = feedbackFilter, nextAttentionRating = attentionRating) {
    const requestId = ++loadRequestId.current;
    setLoading(true);
    setError('');
    clearFeedbackData();
    try {
      const params = {
        platform_code: nextFilter.platform_code || undefined,
        external_product_id: nextFilter.external_product_id || undefined,
      };
      const [summary, reviews, comparisons, scopedOverview] = await Promise.all([
        getSellerFeedbackSummary(params),
        getSellerFeedbackReviews({
          ...params,
          rating: nextAttentionRating || undefined,
          only_attention: true,
          limit: 30,
        }),
        getImageComparisons({ ...params, limit: 30 }),
        getOverview(params),
      ]);
      if (requestId !== loadRequestId.current) return;
      setFeedbackSummary(summary);
      setAttentionReviews(reviews);
      setImageComparisons(comparisons);
      setOverview(scopedOverview);
    } catch {
      if (requestId !== loadRequestId.current) return;
      setError('Chưa tải được seller feedback. Hãy kiểm tra backend và MongoDB.');
    } finally {
      if (requestId === loadRequestId.current) {
        setLoading(false);
      }
    }
  }

  function updateFeedbackFilter(nextFilter: { platform_code: string; external_product_id: string }) {
    setFeedbackFilter(nextFilter);
    clearFeedbackData();
    setProductImages([]);
    setLinkStatus('');
  }

  function updateAttentionRating(nextRating: number) {
    setAttentionRating(nextRating);
    loadSellerFeedback(feedbackFilter, nextRating);
  }

  async function analyzeProductLink() {
    const trimmed = productLink.trim();
    if (!trimmed) {
      setError('Bạn hãy dán link sản phẩm Lazada, Tiki hoặc TikTok Shop trước.');
      return;
    }
    setResolvingLink(true);
    setError('');
    setJobStep('Đang đọc thông tin sản phẩm từ link...');
    setLinkStatus('');
    clearFeedbackData();
    try {
      const resolved = await resolveProductLink(trimmed);
      const nextFilter = {
        platform_code: resolved.platform_code,
        external_product_id: resolved.external_product_id,
      };
      setFeedbackFilter(nextFilter);
      setProductImages(resolved.product_images || []);
      setLinkStatus(
        `${resolved.message} Sàn: ${resolved.platform_code.toUpperCase()}, ID sản phẩm: ${resolved.external_product_id}, ảnh gốc: ${resolved.images_found ?? resolved.product_images?.length ?? 0}.`
      );
      setJobStep('Đã đọc link. Đang tải dashboard hiện có...');
      await loadSellerFeedback(nextFilter);
      setJobStep('');
    } catch {
      setError('Chưa đọc được link này. Hiện tool hỗ trợ link sản phẩm Lazada, Tiki hoặc TikTok Shop.');
      setJobStep('');
    } finally {
      setResolvingLink(false);
    }
  }

  async function fetchProductLinkToMongo() {
    const trimmed = productLink.trim();
    if (!trimmed) {
      setError('Bạn hãy dán link sản phẩm Lazada, Tiki hoặc TikTok Shop trước.');
      return;
    }
    setIngestingLink(true);
    setError('');
    setJobStep('Đang kéo review từ sàn và lưu vào Mongo...');
    setLinkStatus('');
    clearFeedbackData();
    try {
      const result = await ingestProductLink(trimmed);
      const nextFilter = {
        platform_code: result.platform_code,
        external_product_id: result.external_product_id,
      };
      setFeedbackFilter(nextFilter);
      setProductImages(result.product_metadata?.product_images || result.product_images || []);
      if (result.status === 'needs_browser_session' || result.requires_browser_session) {
        setLinkStatus(result.message);
        setIngestingLink(false);
        setJobStep('Đang tải lại dashboard hiện có...');
        await loadSellerFeedback(nextFilter);
        setJobStep('');
        return;
      }
      setLinkStatus(
        `${result.message} Nguồn: ${formatSourceMode(result.source_mode)}, lấy được: ${result.source_reviews}, hợp lệ: ${result.normalized_reviews}, Mongo hiện có: ${result.total_reviews} review, ảnh gốc: ${result.product_metadata?.images_found ?? 0}, ảnh review đã phân tích: ${result.image_analysis?.image_reviews_analyzed ?? 0}/${result.total_reviews_with_images}.`
      );
      setIngestingLink(false);
      setJobStep('Đã kéo xong. Đang tải lại dashboard...');
      await loadSellerFeedback(nextFilter);
      setJobStep('');
    } catch (err: any) {
      if (err?.code === 'ECONNABORTED') {
        setError('Backend xử lý lâu hơn thời gian chờ của trình duyệt. Dữ liệu có thể vẫn đang được lưu; hãy đợi một chút rồi bấm Tải phân tích để xem kết quả mới nhất.');
      } else {
        setError(err?.response?.data?.detail || 'Chưa kéo được API từ link này. Hãy kiểm tra backend hoặc token/cookie của sàn.');
      }
      setJobStep('');
    } finally {
      setIngestingLink(false);
    }
  }

  async function openPlatformBrowserSession() {
    const trimmed = productLink.trim();
    const normalizedLink = trimmed.toLowerCase();
    const platformFromLink = normalizedLink.includes('lazada.vn')
      ? 'lazada'
      : normalizedLink.includes('shop.tiktok.com')
        ? 'tiktok_shop'
        : '';
    const platformCode = platformFromLink || feedbackFilter.platform_code;
    if (!['lazada', 'tiktok_shop'].includes(platformCode)) {
      setError('Phiên trình duyệt hiện chỉ cần cho Lazada hoặc TikTok Shop. Tiki đang dùng API công khai nên không cần mở phiên.');
      return;
    }
    setOpeningBrowserSession(true);
    setError('');
    setJobStep(`Đang mở phiên trình duyệt ${platformCode === 'lazada' ? 'Lazada' : 'TikTok Shop'}...`);
    setLinkStatus('');
    try {
      const result = platformCode === 'lazada'
        ? await openLazadaSession(trimmed || undefined)
        : await openTikTokSession(trimmed || undefined);
      setLinkStatus(`${result.message} Hồ sơ phiên: ${result.profile_dir}`);
      setJobStep('');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        (typeof detail === 'string' && detail.trim())
          ? detail
          : 'Chưa mở được phiên trình duyệt. Hãy tắt server backend rồi chạy lại để backend nhận cấu hình Playwright mới.'
      );
      setJobStep('');
    } finally {
      setOpeningBrowserSession(false);
    }
  }

  async function analyzeImagesForCurrentProduct() {
    const trimmed = productLink.trim();
    if (!trimmed && (!feedbackFilter.platform_code || !feedbackFilter.external_product_id)) {
      setError('Bạn hãy dán link hoặc chọn sản phẩm trước khi phân tích ảnh.');
      return;
    }
    setAnalyzingImages(true);
    setError('');
    setJobStep('Đang phân tích ảnh review với ảnh gốc sản phẩm...');
    setLinkStatus('');
    clearFeedbackData();
    try {
      const result = await analyzeProductImages({
        product_url: trimmed || undefined,
        platform_code: trimmed ? undefined : feedbackFilter.platform_code,
        external_product_id: trimmed ? undefined : feedbackFilter.external_product_id,
        limit: 0,
        max_images_per_review: 2,
      });
      const nextFilter = {
        platform_code: result.platform_code || feedbackFilter.platform_code,
        external_product_id: result.external_product_id || feedbackFilter.external_product_id,
      };
      setFeedbackFilter(nextFilter);
      setProductImages(result.product_metadata.product_images || []);
      setLinkStatus(
        `${result.message} Review có ảnh: ${result.total_reviews_with_images}, đã phân tích: ${result.image_analysis.image_reviews_analyzed}, lỗi: ${result.image_analysis.image_reviews_failed}, ảnh gốc: ${result.product_metadata.images_found}.`
      );
      setAnalyzingImages(false);
      setJobStep('Đã phân tích ảnh. Đang tải lại dashboard...');
      await loadSellerFeedback(nextFilter);
      setJobStep('');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Chưa phân tích được ảnh. Hãy kiểm tra model CLIP, ảnh gốc sản phẩm hoặc kết nối mạng.');
      setJobStep('');
    } finally {
      setAnalyzingImages(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Seller Feedback Intelligence</p>
          <h1>Dashboard kiểm tra review cần chú ý</h1>
        </div>
      </header>

      <section className="seller-feedback">
        <div className="panel-title"><ShieldCheck size={20} /><h2>Bảng điều khiển phân tích</h2></div>
        <div className="link-tool">
          <div className="link-input-wrap">
            <label>
              Link sản phẩm
              <textarea
                value={productLink}
                onChange={e => setProductLink(e.target.value)}
                rows={3}
                placeholder="Dán link Lazada, Tiki hoặc TikTok Shop"
              />
            </label>
            <ProductImagePreview images={productImages} />
          </div>
          <div className="action-panel">
            <button type="button" onClick={analyzeProductLink} disabled={resolvingLink}>
              {resolvingLink ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
              {resolvingLink ? 'Đang đọc' : 'Đọc link'}
            </button>
            <button type="button" onClick={openPlatformBrowserSession} disabled={openingBrowserSession}>
              {openingBrowserSession ? <Loader2 className="spin" size={18} /> : <KeyRound size={18} />}
              {openingBrowserSession ? 'Đang mở' : 'Mở phiên'}
            </button>
            <button className="primary-action" type="button" onClick={fetchProductLinkToMongo} disabled={ingestingLink}>
              {ingestingLink ? <Loader2 className="spin" size={18} /> : <BarChart3 size={18} />}
              {ingestingLink ? 'Đang kéo dữ liệu' : 'Kéo dữ liệu'}
            </button>
          </div>
        </div>
        {jobStep && <p className="job-status"><Loader2 className="spin" size={16} />{jobStep}</p>}
        {linkStatus && <p className="link-status">{linkStatus}</p>}
        <div className="dashboard-bar">
          <div className="filter-row">
            <label>
              Sàn
              <select value={feedbackFilter.platform_code} onChange={e => updateFeedbackFilter({ ...feedbackFilter, platform_code: e.target.value })}>
                <option value="lazada">Lazada</option>
                <option value="tiki">Tiki</option>
                <option value="tiktok_shop">TikTok Shop</option>
              </select>
            </label>
            <label>ID sản phẩm<input value={feedbackFilter.external_product_id} onChange={e => updateFeedbackFilter({ ...feedbackFilter, external_product_id: e.target.value })} /></label>
          </div>
          <div className="secondary-actions">
            <button type="button" onClick={() => loadSellerFeedback()} disabled={loading}>
              {loading ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
              {loading ? 'Đang tải' : 'Tải dashboard'}
            </button>
            <button type="button" onClick={analyzeImagesForCurrentProduct} disabled={analyzingImages}>
              {analyzingImages ? <Loader2 className="spin" size={18} /> : <Camera size={18} />}
              {analyzingImages ? 'Đang phân tích' : 'Phân tích ảnh'}
            </button>
          </div>
        </div>
        <section className="stats-grid">
          <Stat icon={<PackageSearch />} label="Sản phẩm" value={overview?.total_products ?? 0} />
          <Stat icon={<MessageSquareText />} label="Tổng review" value={overview?.total_reviews ?? 0} />
          <Stat icon={<Camera />} label="Review có ảnh" value={overview?.total_reviews_with_images ?? 0} />
          <Stat icon={<AlertTriangle />} label="Cần kiểm tra" value={overview?.total_reviews_need_seller_attention ?? 0} />
        </section>
        {error && <p className="error">{error}</p>}
        {feedbackSummary ? (
          <SellerFeedbackView
            filter={feedbackFilter}
            summary={feedbackSummary}
            reviews={attentionReviews}
            imageComparisons={imageComparisons}
            attentionRating={attentionRating}
            onAttentionRatingChange={updateAttentionRating}
          />
        ) : <p className="empty">Chưa có dữ liệu phân tích cho bộ lọc hiện tại.</p>}
      </section>
    </main>
  );
}

function Stat({ icon, label, value }: { icon: JSX.Element; label: string; value: number }) {
  return <div className="stat">{icon}<span>{label}</span><strong>{value.toLocaleString()}</strong></div>;
}

function ProductImagePreview({ images }: { images: string[] }) {
  const preview = images.filter(Boolean).slice(0, 3);
  return (
    <div className="product-preview">
      <span>Ảnh gốc sản phẩm</span>
      {preview.length > 0 ? (
        <div className="product-preview-images">
          {preview.map(url => (
            <a key={url} href={url} target="_blank" rel="noreferrer">
              <img src={url} alt="Ảnh gốc sản phẩm dùng để so sánh" loading="lazy" />
            </a>
          ))}
        </div>
      ) : (
        <p>Chưa có ảnh gốc. Bấm Kéo dữ liệu hoặc Phân tích ảnh để hệ thống lấy ảnh từ link sản phẩm.</p>
      )}
    </div>
  );
}

function SellerFeedbackView({
  filter,
  summary,
  reviews,
  imageComparisons,
  attentionRating,
  onAttentionRatingChange,
}: {
  filter: { platform_code: string; external_product_id: string };
  summary: SellerFeedbackSummary;
  reviews: SellerReviewDecision[];
  imageComparisons: ImageComparison[];
  attentionRating: number;
  onAttentionRatingChange: (rating: number) => void;
}) {
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null);
  const selectedReview = selectedReviewId ? reviews.find(review => review.review_id === selectedReviewId) : undefined;
  const selectedComparison = selectedReviewId ? imageComparisons.find(item => item.review_id === selectedReviewId) : undefined;

  function openReviewDetail(reviewId: number) {
    setSelectedReviewId(reviewId);
    window.setTimeout(() => {
      document.getElementById('review-detail-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  }

  return (
    <div className="feedback-stack">
      <p className="filter-note">
        Đang xem riêng sản phẩm {filter.platform_code.toUpperCase()} / {filter.external_product_id}. Bảng review bên dưới đang hiển thị {reviews.length} review cần chú ý mới nhất; bảng ảnh đang hiển thị {imageComparisons.length} review có ảnh mới nhất.
      </p>
      <div className="summary-strip">
        <span>Đã đọc ảnh: {summary.reviews_with_image_analysis}/{summary.reviews_with_images}</span>
        <span>Review &lt;=3 sao bị flag: {summary.flagged_reviews}</span>
        <span>Trust trung bình: {summary.average_trust_score}</span>
        <span>Độ tin cậy: {formatCounts(summary.trust_level_counts)}</span>
      </div>
      {(selectedReview || selectedComparison) && (
        <ReviewDetailPanel
          review={selectedReview}
          comparison={selectedComparison}
          onClose={() => setSelectedReviewId(null)}
        />
      )}
      <div className="table-heading">
        <div>
          <h3>Review cần seller chú ý</h3>
          <p>Bảng này ưu tiên review từ 3 sao trở xuống có độ tin cậy thấp hoặc bị flag, sắp xếp theo comment mới nhất trước.</p>
        </div>
        <label className="compact-select">
          Lọc sao
          <select value={attentionRating} onChange={event => onAttentionRatingChange(Number(event.target.value))}>
            <option value={0}>Tất cả</option>
            <option value={1}>1 sao</option>
            <option value={2}>2 sao</option>
            <option value={3}>3 sao</option>
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Review</th>
              <th>Sàn</th>
              <th>Sao</th>
              <th>Ảnh có phù hợp?</th>
              <th>Bằng chứng</th>
              <th>Độ tin cậy</th>
              <th>Seller cần làm gì?</th>
            </tr>
          </thead>
          <tbody>
            {reviews.map(review => (
              <tr key={review.review_id}>
                <td>
                  <button className="text-button" type="button" onClick={() => openReviewDetail(review.review_id)}>
                    #{review.external_review_id}
                  </button>
                  <p>{review.review_text || 'Review không có nội dung chữ.'}</p>
                  {review.image_urls.length > 0 && <a href={review.image_urls[0]} target="_blank" rel="noreferrer">Mở ảnh review</a>}
                </td>
                <td>{review.source || review.platform_code}</td>
                <td>{review.rating}</td>
                <td><b>{review.image_fit.score}</b><span>{review.image_fit.answer}</span></td>
                <td><b>{translateEvidenceLabel(review.evidence.label)}</b><span>{review.evidence.answer}</span></td>
                <td><b>{review.trust.score}</b><span>{review.trust.level}</span></td>
                <td><b>{review.seller_action.priority}</b><span>{review.seller_action.answer}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel-title image-title"><Camera size={20} /><h2>Kiểm tra ảnh review</h2></div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ảnh</th>
              <th>Review</th>
              <th>Trạng thái</th>
              <th>Điểm tổng</th>
              <th>Ảnh vs chữ</th>
              <th>Ảnh vs ảnh SP</th>
              <th>Ảnh vs nội dung review</th>
              <th>Nhãn mong đợi</th>
            </tr>
          </thead>
          <tbody>
            {imageComparisons.map(item => (
              <tr key={item.review_id}>
                <td>{item.image_urls[0] ? <a href={item.image_urls[0]} target="_blank" rel="noreferrer">Mở ảnh</a> : 'Không có ảnh'}</td>
                <td>
                  <button className="text-button" type="button" onClick={() => openReviewDetail(item.review_id)}>
                    {item.source || item.platform_code} #{item.external_review_id}
                  </button>
                  <p>{item.review_text || 'Review không có nội dung chữ.'}</p>
                </td>
                <td>
                  <b>{formatAnalysisStatus(item.analysis_status)}</b>
                  {item.image_evidence_status !== item.analysis_status && <span>{translateImageStatus(item.image_evidence_status)}</span>}
                </td>
                <td>{formatScore(item.image_relevance_score)}</td>
                <td>{formatScore(item.text_score)}</td>
                <td>{formatScore(item.product_image_score)}</td>
                <td>
                  <b>{formatScore(item.claim_evidence_score)}</b>
                  <span>{translateClaimType(item.review_claim_type)}</span>
                  <span>{translateClaimStatus(item.claim_evidence_status)}</span>
                </td>
                <td><span>{formatLabelList([...item.expected_product_labels, ...item.expected_evidence_labels])}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReviewDetailPanel({
  review,
  comparison,
  onClose,
}: {
  review?: SellerReviewDecision;
  comparison?: ImageComparison;
  onClose: () => void;
}) {
  const reviewId = review?.external_review_id || comparison?.external_review_id || '';
  const source = review?.source || comparison?.source || review?.platform_code || comparison?.platform_code || '';
  const rating = review?.rating ?? comparison?.rating;
  const createdAt = review?.created_at || comparison?.created_at;
  const trust = review?.trust || comparison?.trust;
  const text = review?.review_text || comparison?.review_text || 'Review không có nội dung chữ.';
  const imageUrls = review?.image_urls?.length ? review.image_urls : comparison?.image_urls || [];
  const sellerAction = review?.seller_action;
  const replyDraft = buildReplyDraft(text, rating, sellerAction?.label);
  const [replyText, setReplyText] = useState(replyDraft);
  const [copyStatus, setCopyStatus] = useState('');
  const sourceUrl = review?.review_source_url || comparison?.review_source_url || review?.product_url || comparison?.product_url;

  useEffect(() => {
    setReplyText(replyDraft);
    setCopyStatus('');
  }, [replyDraft, reviewId]);

  async function copyReplyText() {
    await navigator.clipboard.writeText(replyText);
    setCopyStatus('Đã copy phản hồi. Seller có thể dán vào ô trả lời trên sàn.');
  }

  return (
    <section className="review-detail" id="review-detail-panel">
      <div className="detail-header">
        <div>
          <p className="eyebrow">Chi tiết review</p>
          <h3>{source} #{reviewId}</h3>
          {sourceUrl && (
            <a className="detail-source-link" href={sourceUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={15} /> Mở trang sản phẩm trên sàn
            </a>
          )}
        </div>
        <button className="icon-button" type="button" aria-label="Đóng chi tiết" onClick={onClose}><X size={18} /></button>
      </div>
      <div className="detail-grid">
        <div>
          <dl className="detail-list">
            <div><dt>Số sao</dt><dd>{rating ?? 'Chưa có'}</dd></div>
            <div><dt>Ngày comment</dt><dd>{formatDateOnly(createdAt)}</dd></div>
            <div><dt>Độ tin cậy</dt><dd>{trust ? `${trust.score} - ${trust.level}` : 'Chưa có'}</dd></div>
          </dl>
          <blockquote>{text}</blockquote>
          {review?.flags?.length ? <p className="flag-line">Dấu hiệu: {review.flags.map(translateFlag).join(', ')}</p> : null}
        </div>
        <div>
          <div className="image-grid">
            {imageUrls.length > 0 ? imageUrls.slice(0, 4).map(url => (
              <a key={url} href={url} target="_blank" rel="noreferrer" className="review-image-link">
                <img src={url} alt={`Ảnh review ${reviewId}`} loading="lazy" />
              </a>
            )) : <p className="empty">Review này không có ảnh.</p>}
          </div>
        </div>
      </div>
      <label className="reply-box">
        Phản hồi gợi ý cho seller
        <textarea value={replyText} onChange={event => setReplyText(event.target.value)} rows={4} />
      </label>
      <div className="reply-actions">
        <button type="button" onClick={copyReplyText}>Copy phản hồi</button>
        {copyStatus && <span>{copyStatus}</span>}
      </div>
    </section>
  );
}

function buildReplyDraft(reviewText: string, rating?: number, actionLabel?: string) {
  if (actionLabel === 'CHECK_IMAGE_OR_REPORT') {
    return 'Shop xin lỗi vì trải nghiệm chưa tốt của bạn. Shop đã ghi nhận phản hồi và sẽ kiểm tra lại hình ảnh, đơn hàng cũng như tình trạng sản phẩm để xử lý phù hợp.';
  }
  if ((rating ?? 5) <= 3) {
    return 'Shop xin lỗi vì trải nghiệm của bạn chưa như mong đợi. Shop đã ghi nhận phản hồi này và sẽ kiểm tra lại đơn hàng để hỗ trợ bạn tốt hơn.';
  }
  if (reviewText.length < 20) {
    return 'Cảm ơn bạn đã đánh giá sản phẩm. Shop rất vui khi nhận được phản hồi từ bạn.';
  }
  return 'Cảm ơn bạn đã chia sẻ phản hồi. Shop sẽ ghi nhận ý kiến này để cải thiện sản phẩm và dịch vụ tốt hơn.';
}

function formatScore(value?: number | null) {
  return typeof value === 'number' ? value.toFixed(2) : 'Chưa phân tích';
}

function formatSourceMode(value?: string) {
  return value === 'browser_session' ? 'phiên trình duyệt' : 'API';
}

function formatAnalysisStatus(value: string) {
  return value === 'analyzed' ? 'Đã phân tích' : 'Chưa phân tích ảnh';
}

function formatDateOnly(value?: string) {
  if (!value) return 'Chưa có';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'short',
  }).format(date);
}

function formatCounts(counts: Record<string, number>, translateKey: (value: string) => string = value => value) {
  return Object.entries(counts).map(([key, value]) => `${translateKey(key)}: ${value}`).join(', ') || 'chưa có';
}

function translateValue(value: string | undefined | null, labels: Record<string, string>) {
  if (!value) return '';
  return labels[value] || value;
}

function translateEvidenceLabel(value: string) {
  return translateValue(value, {
    STRONG: 'Mạnh',
    ENOUGH_TO_REFERENCE: 'Có thể tham khảo',
    WEAK: 'Yếu',
    RATING_ONLY: 'Chỉ có sao',
  });
}

function translateFlag(value: string) {
  return translateValue(value, {
    low_rating_without_clear_reason: 'sao thấp nhưng lý do chưa rõ',
    rating_text_mismatch: 'số sao và nội dung bị lệch',
    image_may_not_match_product: 'ảnh có dấu hiệu không khớp sản phẩm',
    image_does_not_support_review_claim: 'ảnh không hỗ trợ nội dung review',
    negative_review_image_does_not_support_claim: 'review tiêu cực nhưng ảnh không đủ chứng minh',
    weak_text_and_weak_image_evidence: 'nội dung và ảnh đều yếu',
    high_rating_with_complaint: 'sao cao nhưng có phàn nàn',
    rating_only_review: 'chỉ có sao, không có nội dung',
  });
}

function translateImageStatus(value: string | undefined) {
  return translateValue(value, {
    image_likely_matches_product: 'Ảnh có khả năng khớp sản phẩm',
    image_possibly_matches_product: 'Ảnh có vẻ liên quan đến sản phẩm',
    image_unclear: 'Ảnh chưa đủ rõ để kết luận',
    image_may_not_match_product: 'Ảnh có dấu hiệu không khớp sản phẩm',
    image_present_not_verified: 'Có ảnh nhưng chưa phân tích',
    image_present_not_verified_by_model: 'Có ảnh nhưng model chưa xác minh',
    no_review_image: 'Không có ảnh review',
    not_analyzed: 'Chưa phân tích ảnh',
  });
}

function translateClaimType(value: string | undefined) {
  return translateValue(value, {
    general_product_feedback: 'Phản hồi chung về sản phẩm',
    product_quality_feedback: 'Nhận xét chất lượng sản phẩm',
    shipping_packaging_damage: 'Khiếu nại giao hàng/đóng gói',
    product_damage_or_defect: 'Khiếu nại sản phẩm lỗi/hư hỏng',
    wrong_or_missing_item: 'Sai hoặc thiếu hàng',
    authenticity_or_label_issue: 'Nghi vấn tem/nhãn/chính hãng',
    not_checked: 'Chưa kiểm tra nội dung ảnh',
  }) || 'Chưa phân loại';
}

function translateClaimStatus(value: string | undefined) {
  return translateValue(value, {
    claim_evidence_likely_matches: 'Ảnh có hỗ trợ nội dung review',
    claim_evidence_unclear: 'Ảnh chưa đủ rõ so với nội dung review',
    claim_evidence_mismatch_risk: 'Ảnh không hỗ trợ nội dung review',
    claim_evidence_not_checked: 'Chưa kiểm tra bằng chứng ảnh',
  });
}

function translateLabel(value: string | undefined | null) {
  return translateValue(value, {
    'the purchased product': 'sản phẩm đã mua',
    'the product described in the review': 'sản phẩm được nhắc trong review',
    'a customer review product photo': 'ảnh sản phẩm do khách chụp',
    'a close up of the product': 'ảnh cận cảnh sản phẩm',
    'a product quality issue': 'vấn đề chất lượng sản phẩm',
    'a normal product photo': 'ảnh sản phẩm bình thường',
    'a random unrelated photo': 'ảnh không liên quan',
    'a random screenshot': 'ảnh chụp màn hình không liên quan',
    'a screenshot': 'ảnh chụp màn hình',
    'a receipt only': 'chỉ là hóa đơn',
    'a food item': 'đồ ăn',
    'a cosmetic bottle': 'chai/lọ mỹ phẩm',
    'a cardboard shipping box only': 'chỉ là thùng/hộp giao hàng',
    'a document or receipt only': 'chỉ là giấy tờ/hóa đơn',
    'a pair of pants or trousers': 'quần dài',
    'a pair of shorts': 'quần short',
    'a book': 'sách',
    'a printed book': 'sách in',
    'a cookbook': 'sách nấu ăn',
    'a mobile phone': 'điện thoại',
    'a shirt': 'áo',
    'a t-shirt': 'áo thun',
    'a clothing top': 'áo mặc trên',
    'a hoodie or sweatshirt': 'áo hoodie/sweatshirt',
    'a pair of jeans': 'quần jeans',
    'a pair of shoes': 'giày',
    'a sneaker': 'giày sneaker',
    'a bag': 'túi',
    'a backpack': 'ba lô',
    'a smartphone': 'điện thoại thông minh',
    'a pair of earphones': 'tai nghe',
    headphones: 'tai nghe',
    'a cosmetic product': 'mỹ phẩm',
    'a snack package': 'gói đồ ăn vặt',
    'a damaged product': 'sản phẩm bị hư hỏng',
    'a broken product': 'sản phẩm bị vỡ/hỏng',
    'a defective product': 'sản phẩm bị lỗi',
    'visible product damage': 'hư hỏng nhìn thấy được',
    'a product quality defect': 'lỗi chất lượng sản phẩm',
    'a dented shipping package': 'kiện hàng bị móp',
    'a damaged cardboard box': 'thùng/hộp bị hư',
    'a crushed parcel': 'kiện hàng bị bẹp',
    'torn product packaging': 'bao bì sản phẩm bị rách',
    'damaged delivery packaging': 'bao bì giao hàng bị hỏng',
    'the wrong delivered product': 'giao sai sản phẩm',
    'a product different from the listing': 'sản phẩm khác mô tả',
    'missing items in the package': 'thiếu hàng trong kiện',
    'a mismatch between ordered item and received item': 'hàng nhận không đúng hàng đặt',
    'a product label or logo': 'nhãn hoặc logo sản phẩm',
    'a product seal': 'tem niêm phong sản phẩm',
    'a barcode on packaging': 'mã vạch trên bao bì',
    'authenticity information on the package': 'thông tin chính hãng trên bao bì',
  });
}

function formatLabelList(values: string[] = []) {
  const translated = Array.from(new Set(values.map(translateLabel).filter(Boolean)));
  return translated.length > 0 ? translated.join(', ') : 'Chưa có';
}

export default App;
