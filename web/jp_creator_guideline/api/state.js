import { list, put, del } from '@vercel/blob';

// 덮어쓰기(동일 경로)는 CDN 전파가 최대 60초 지연되므로,
// 저장마다 새 경로(state-<ts>.json)에 불변 객체로 쓰고 최신본을 읽는다.
const PREFIX = 'guideline-1a/state-';
const EMPTY = { edits: {}, updatedAt: null };

function tsOf(pathname) {
  const m = /state-(\d+)\.json$/.exec(pathname);
  return m ? Number(m[1]) : 0;
}

async function listStates() {
  const { blobs } = await list({ prefix: PREFIX });
  return blobs.sort((a, b) => tsOf(b.pathname) - tsOf(a.pathname));
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.method === 'GET') {
      const blobs = await listStates();
      if (!blobs.length) return res.status(200).json(EMPTY);
      const r = await fetch(blobs[0].url, { cache: 'no-store' });
      if (!r.ok) return res.status(200).json(EMPTY);
      return res.status(200).json(await r.json());
    }
    if (req.method === 'POST') {
      const body = req.body || {};
      const edits = body.edits && typeof body.edits === 'object' && !Array.isArray(body.edits) ? body.edits : {};
      const payload = JSON.stringify({ edits, updatedAt: new Date().toISOString() });
      if (payload.length > 500_000) {
        return res.status(413).json({ error: 'payload too large' });
      }
      await put(`${PREFIX}${Date.now()}.json`, payload, {
        access: 'public',
        addRandomSuffix: false,
        contentType: 'application/json',
      });
      // 오래된 버전 정리 (최근 5개 유지, 실패해도 무시)
      try {
        const blobs = await listStates();
        const old = blobs.slice(5);
        if (old.length) await del(old.map((b) => b.url));
      } catch {}
      return res.status(200).json({ ok: true });
    }
    res.setHeader('Allow', 'GET, POST');
    return res.status(405).json({ error: 'method not allowed' });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
}
