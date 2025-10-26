/**
 * 在旧版 Node 环境中填充全局 Web Crypto 能力，确保 Vite 构建可用。
 */
(() => {
  const crypto = require('crypto');

  const ensureGetRandomValues = (target) => {
    if (!target || typeof target.getRandomValues === 'function') {
      return target;
    }
    if (typeof crypto.randomFillSync !== 'function') {
      throw new Error('当前 Node 环境缺少 randomFillSync，无法模拟 Web Crypto。');
    }
    target.getRandomValues = (typedArray) => {
      if (!typedArray || typeof typedArray.length !== 'number') {
        throw new TypeError('Expected a typed array');
      }
      crypto.randomFillSync(typedArray);
      return typedArray;
    };
    return target;
  };

  const ensureRandomUUID = (target) => {
    if (!target) return target;
    if (typeof target.randomUUID !== 'function' && typeof crypto.randomUUID === 'function') {
      target.randomUUID = () => crypto.randomUUID();
    }
    return target;
  };

  if (typeof globalThis.crypto !== 'undefined') {
    ensureGetRandomValues(globalThis.crypto);
    ensureRandomUUID(globalThis.crypto);
    if (typeof globalThis.crypto.getRandomValues === 'function') {
      return;
    }
  }

  const webcrypto = ensureRandomUUID(ensureGetRandomValues(crypto.webcrypto));
  if (webcrypto && typeof webcrypto.getRandomValues === 'function') {
    globalThis.crypto = webcrypto;
  } else {
    const polyfill = ensureRandomUUID({});
    ensureGetRandomValues(polyfill);
    globalThis.crypto = polyfill;
  }

  // 同时修补 require('crypto') 本身，以兼容直接引用 crypto.getRandomValues 的情况
  ensureGetRandomValues(crypto);
  ensureRandomUUID(crypto);
})();
