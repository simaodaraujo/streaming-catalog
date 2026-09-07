/**
 * Stremio Subtitles Addon - Motor de Legendas PT-PT para Vercel Serverless
 * Suporta filmes, séries e animes com filtragem estrita em Português de Portugal (PT-PT).
 * Cache CDN de 24 horas para consumo zero de créditos e latência mínima.
 */

const https = require('https');

// Helper para pedidos HTTP rápidos nativos (Node.js)
function fetchJson(url) {
  return new Promise((resolve) => {
    const req = https.get(
      url,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)',
          'Accept': 'application/json',
        },
        timeout: 5000,
      },
      (res) => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          res.resume();
          return resolve(null);
        }
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            resolve(null);
          }
        });
      }
    );

    req.on('error', () => resolve(null));
    req.on('timeout', () => {
      req.destroy();
      resolve(null);
    });
  });
}

// Resolver ID do Kitsu (anime) para ID do IMDb
async function resolveKitsuToImdb(kitsuId) {
  try {
    const kitsuData = await fetchJson(`https://kitsu.io/api/edge/anime/${kitsuId}`);
    if (!kitsuData || !kitsuData.data || !kitsuData.data.attributes) return null;

    const titles = kitsuData.data.attributes.titles || {};
    const queryTitle = titles.en || titles.en_jp || kitsuData.data.attributes.canonicalTitle;
    if (!queryTitle) return null;

    // Pesquisar no Cinemeta Stremio
    const cinemeta = await fetchJson(`https://v3-cinemeta.strem.io/catalog/series/top/search=${encodeURIComponent(queryTitle)}.json`);
    if (cinemeta && cinemeta.metas && cinemeta.metas.length > 0) {
      return cinemeta.metas[0].id; // Retorna ex: "tt2560140"
    }
  } catch (e) {
    // Ignorar erros de resolução de anime
  }
  return null;
}

module.exports = async (req, res) => {
  // Configurar cabeçalhos CORS obrigatórios do Stremio
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  // Cache Edge de 24h na CDN da Vercel (economiza 100% de chamadas repetidas)
  res.setHeader('Cache-Control', 'public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    // Extrair parâmetros da URL
    let type = req.query.type;
    let id = req.query.id;
    let extra = req.query.extra || '';

    if (type) type = String(type).replace(/\.json$/, '');
    if (id) id = String(id).replace(/\.json$/, '');
    if (extra) extra = String(extra).replace(/\.json$/, '');

    // Fallback se recebido via path rewrite
    if (!type || !id) {
      let rawPath = req.query.path || '';
      if (!rawPath && req.url) {
        const urlMatch = req.url.match(/subtitles\/(.+)/);
        if (urlMatch) rawPath = urlMatch[1];
      }
      rawPath = rawPath.replace(/\.json$/, '');
      const parts = rawPath.split('/').filter(Boolean);
      type = type || parts[0];
      id = id || parts[1];
      if (parts.length > 2) {
        extra = extra || parts.slice(2).join('/');
      }
    }

    if (!type || !id) {
      return res.status(200).json({ subtitles: [] });
    }

    // Suporte a animes do Kitsu (kitsu:ID:EP)
    if (id.startsWith('kitsu:')) {
      const kParts = id.split(':');
      const kitsuAnimeId = kParts[1];
      const epNum = kParts[2] || '1';
      const imdbSeriesId = await resolveKitsuToImdb(kitsuAnimeId);
      if (imdbSeriesId) {
        id = `${imdbSeriesId}:1:${epNum}`;
        type = 'series';
      }
    }

    // Consultar o OpenSubtitles v3 (proxy oficial com todo o acervo do OpenSubtitles)
    const extraEncoded = extra ? `/${encodeURIComponent(extra)}` : '';
    const osUrl = `https://opensubtitles-v3.strem.io/subtitles/${encodeURIComponent(type)}/${encodeURIComponent(id)}${extraEncoded}.json`;

    const data = await fetchJson(osUrl);
    if (!data || !Array.isArray(data.subtitles)) {
      return res.status(200).json({ subtitles: [] });
    }

    // FILTRO RIGOROSO:
    // lang === 'por' corresponde a Português de Portugal (PT-PT)
    // lang === 'pob' corresponde a Português do Brasil (PT-BR) -> DESCARTADO
    const ptPtSubs = data.subtitles
      .filter((s) => s.lang === 'por')
      .map((s, index) => ({
        id: s.id || `ptpt-${index + 1}`,
        url: s.url,
        lang: 'por',
        format: s.format || 'srt',
        // Metadados adicionais úteis para o player
        SubEncoding: s.SubEncoding || 'UTF-8',
        subtitleFileName: s.subtitleFileName,
        movieReleaseName: s.movieReleaseName,
      }));

    return res.status(200).json({ subtitles: ptPtSubs });
  } catch (err) {
    console.error('Erro no processamento de legendas PT-PT:', err);
    return res.status(200).json({ subtitles: [] });
  }
};
