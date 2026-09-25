// Optional semantic ranking with an open-source multilingual embedding model that runs
// entirely in the browser (Transformers.js + ONNX/WebAssembly). No API key, no tokens.
// The model (~120 MB, quantized) downloads once and is then cached by the browser.

const MODEL = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
let extractorPromise = null;

async function getExtractor(onProgress) {
  if (!extractorPromise) {
    extractorPromise = (async () => {
      const { pipeline, env } = await import("https://cdn.jsdelivr.net/npm/@huggingface/transformers@3");
      env.allowLocalModels = false;
      return pipeline("feature-extraction", MODEL, {
        dtype: "q8",
        progress_callback: (p) => {
          if (p.status === "progress" && p.total) onProgress?.(`下載模型 ${Math.round((p.loaded / p.total) * 100)}%`);
        },
      });
    })().catch((e) => { extractorPromise = null; throw e; });
  }
  return extractorPromise;
}

function cosine(a, b) {
  let dot = 0;
  for (let i = 0; i < a.length; i++) dot += a[i] * b[i];
  return dot; // vectors are already normalized
}

/** Returns Map(text -> similarity 0..1) between each text and the job description. */
export async function semanticScores(jobText, texts, onProgress) {
  const extractor = await getExtractor(onProgress);
  onProgress?.("計算語意相似度…");
  const unique = [...new Set(texts)].filter(Boolean);
  const out = await extractor([jobText, ...unique], { pooling: "mean", normalize: true });
  const vecs = out.tolist();
  const scores = new Map();
  unique.forEach((t, i) => scores.set(t, Math.max(0, cosine(vecs[0], vecs[i + 1]))));
  return scores;
}
