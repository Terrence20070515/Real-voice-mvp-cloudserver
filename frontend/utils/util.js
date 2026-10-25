// utils/util.js — 通用工具函数

const util = {
  /**
   * 生成 session_id
   * 优先用 crypto.randomUUID()（高版本基础库支持），否则用时间戳+随机数
   * @returns {string} 形如 "sess_xxxxxxxx"
   */
  generateSessionId() {
    let uuid = '';
    try {
      if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        uuid = crypto.randomUUID();
      }
    } catch (e) {
      uuid = '';
    }
    if (!uuid) {
      // 回退方案：时间戳 + 随机数
      const timestamp = Date.now().toString(36);
      const random = Math.random().toString(36).substring(2, 10);
      uuid = timestamp + '_' + random;
    }
    return 'sess_' + uuid;
  },

  /**
   * 获取持久化的 session_id
   * 如果 storage 里没有就生成一个新的并保存
   * @returns {string}
   */
  getSessionId() {
    let sid = '';
    try {
      sid = wx.getStorageSync('session_id');
    } catch (e) {
      sid = '';
    }
    if (!sid) {
      sid = this.generateSessionId();
      try {
        wx.setStorageSync('session_id', sid);
      } catch (e) {
        /* ignore */
      }
    }
    return sid;
  },

  /**
   * 清除持久化的 session_id（下次进入会生成新的）
   */
  clearSessionId() {
    try {
      wx.removeStorageSync('session_id');
    } catch (e) {
      /* ignore */
    }
  },

  /**
   * 保存 session_id 到 storage
   */
  saveSessionId(sid) {
    try {
      wx.setStorageSync('session_id', sid);
    } catch (e) {
      /* ignore */
    }
  },

  // ─── 聊天记录持久化（按 sessionId 存储）───
  /**
   * 保存聊天记录
   * @param {string} sessionId
   * @param {Array} messages
   */
  saveChatHistory(sessionId, messages) {
    if (!sessionId || !messages) return;
    try {
      // 限制最大保存 100 条，避免 storage 爆掉
      const toSave = messages.length > 100 ? messages.slice(-100) : messages;
      wx.setStorageSync('chat_history_' + sessionId, toSave);
    } catch (e) {
      /* storage 满了之类的，忽略 */
    }
  },

  /**
   * 加载聊天记录
   * @param {string} sessionId
   * @returns {Array}
   */
  loadChatHistory(sessionId) {
    if (!sessionId) return [];
    try {
      return wx.getStorageSync('chat_history_' + sessionId) || [];
    } catch (e) {
      return [];
    }
  },

  /**
   * 清除某个会话的聊天记录
   */
  clearChatHistory(sessionId) {
    if (!sessionId) return;
    try {
      wx.removeStorageSync('chat_history_' + sessionId);
    } catch (e) {
      /* ignore */
    }
  },

  /**
   * 格式化时间 HH:MM
   * @param {Date|number} date
   * @returns {string}
   */
  formatTime(date) {
    const d = date instanceof Date ? date : new Date(date || Date.now());
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return hours + ':' + minutes;
  },

  /**
   * 判断字符串是否包含中文
   */
  hasChinese(str) {
    return /[\u4e00-\u9fa5]/.test(str || '');
  },

  // ─────────────────────────────────────────────
  //  菜单与店名：全部由后端菜单驱动，前端零硬编码
  //  （店名规则：后端给 restaurant 就用；没给则按菜单内容推断菜系；都推不出用「本店」，
  //    与后端 agent.py 的 _get_restaurant_name() 兜底保持一致）
  // ─────────────────────────────────────────────

  /** 安全转字符串：脏数据一律当空，避免渲染出 undefined / [object Object] */
  safeStr(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    return '';
  },

  /**
   * 菜单规范化：兼容三种后端返回
   *   1. 扁平数组（当前线上）  2. {restaurant, items}  3. {restaurant, categories}
   * 对脏数据零信任：null / 非对象 / 缺菜名的元素直接丢弃，
   * 绝不让一条坏数据把整个菜单搞崩。
   * @returns {{restaurant: (string|null), groups: Array, total: number}}
   */
  normalizeMenu(raw) {
    const out = { restaurant: null, groups: [], total: 0 };

    const pick = (it, catName) => {
      if (!it || typeof it !== 'object' || Array.isArray(it)) return null;
      const name = this.safeStr(it['菜品']) || this.safeStr(it.name) || this.safeStr(it.dish_name);
      if (!name) return null;
      return {
        cat: this.safeStr(catName) || this.safeStr(it['分类']) || this.safeStr(it.category) || '其他',
        name: name,
        price: this.safeStr(it['价格']) || this.safeStr(it.price),
        spicy: this.safeStr(it['辣度']) || this.safeStr(it.spicy),
        desc: this.safeStr(it['描述']) || this.safeStr(it.description),
        allergens: this.safeStr(it['过敏原']) || this.safeStr(it.allergens)
      };
    };

    const add = (it, catName) => {
      const d = pick(it, catName);
      if (!d) return;
      let g = out.groups.find(x => x.name === d.cat);
      if (!g) { g = { name: d.cat, items: [] }; out.groups.push(g); }
      g.items.push(d);
      out.total++;
    };

    if (Array.isArray(raw)) {
      raw.forEach(it => add(it));
    } else if (raw && typeof raw === 'object') {
      out.restaurant = raw.restaurant || raw.shop_name || null;
      if (Array.isArray(raw.items)) {
        raw.items.forEach(it => add(it));
      } else if (Array.isArray(raw.categories)) {
        raw.categories.forEach(c => {
          if (!c || typeof c !== 'object') return;
          (Array.isArray(c.items) ? c.items : []).forEach(it => add(it, c.name));
        });
      }
    }
    return out;
  },

  /** 菜系关键词表（用于后端未提供店名时的推断） */
  CUISINES: [
    { name: '川菜', keys: ['热菜·川味', '川味', '川菜', '麻辣', '水煮', '回锅', '宫保', '麻婆', '夫妻肺片',
        '口水鸡', '毛血旺', '辣子鸡', '酸菜鱼', '担担', '冒菜', '豆瓣', '花椒', '鱼香', '钵钵鸡', '串串', '辣'] },
    { name: '日料', keys: ['日式', '日料', '寿司', '刺身', '天妇罗', '味噌', '拉面', '鳗鱼', '照烧', '亲子丼',
        '清酒', '芥末', '三文鱼', '金枪鱼', '乌冬', '居酒屋', '手卷', '军舰', '茶碗蒸'] },
    { name: '粤菜', keys: ['粤菜', '粤式', '港式', '虾饺', '烧卖', '叉烧', '白灼', '肠粉', '煲仔', '老火',
        '艇仔', '凤爪', '砂锅粥', '蒸排骨'] },
    { name: '湘菜', keys: ['湘菜', '剁椒', '小炒肉', '口味虾', '臭豆腐', '外婆菜', '擂辣椒'] },
    { name: '韩餐', keys: ['韩式', '韩餐', '泡菜', '石锅', '拌饭', '年糕', '部队锅', '大酱汤', '冷面', '烤肉'] },
    { name: '泰餐', keys: ['泰式', '泰餐', '冬阴功', '青木瓜', '打抛', '椰浆', '绿咖喱', '菠萝饭'] },
    { name: '西餐', keys: ['牛排', '意面', '披萨', '汉堡', '罗宋', '提拉米苏', '帕尼尼', '沙拉'] }
  ],

  /**
   * 按菜单内容推断菜系；证据不足返回 null（宁可不猜）
   * 分类名命中权重高（如「热菜·川味」），菜名/描述按命中菜品数计分、单分类封顶，避免长菜单刷分。
   */
  inferCuisine(groups) {
    if (!groups || !groups.length) return null;
    let best = null, bestScore = 0;

    this.CUISINES.forEach(cu => {
      let score = 0;
      groups.forEach(g => {
        const gName = this.safeStr(g.name);
        if (cu.keys.some(k => gName.indexOf(k) >= 0)) score += 3;
        let dishHit = 0;
        (g.items || []).forEach(d => {
          const text = this.safeStr(d.name) + ' ' + this.safeStr(d.desc);
          if (cu.keys.some(k => text.indexOf(k) >= 0)) dishHit++;
        });
        score += Math.min(dishHit, 5);
      });
      if (score > bestScore) { bestScore = score; best = cu.name; }
    });

    return bestScore >= 4 ? best : null;
  },

  /** 最终展示的店名：后端字段 > 菜系推断 > 「本店」 */
  displayName(restaurant, groups) {
    const r = this.safeStr(restaurant).trim();
    if (r) return r;
    return this.inferCuisine(groups) || '本店';
  },

  /** 编辑距离（短字符串，用于菜名同音字纠错） */
  editDistance(a, b) {
    if (a === b) return 0;
    const m = a.length;
    const n = b.length;
    if (!m) return n;
    if (!n) return m;
    let prev = [];
    for (let j = 0; j <= n; j++) prev[j] = j;
    for (let i = 1; i <= m; i++) {
      const cur = [i];
      for (let j = 1; j <= n; j++) {
        const cost = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1;
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
      }
      prev = cur;
    }
    return prev[n];
  },

  /**
   * 用当前菜单纠正语音识别里的菜名同音字（虾饺黄 → 虾饺皇、干炒牛和 → 干炒牛河）
   * menuData: [{ name, items: [{ name }] }]
   * 只对长度 >= 3 的菜名做编辑距离 1 的替换；2 字菜名不做模糊匹配，避免误伤
   */
  correctDishNames(text, menuData) {
    const src = this.safeStr(text);
    if (!src || !Array.isArray(menuData) || !menuData.length) return src;

    const names = [];
    menuData.forEach((cat) => {
      (cat.items || []).forEach((d) => {
        const n = this.safeStr(d && d.name).trim();
        if (n && names.indexOf(n) < 0) names.push(n);
      });
    });
    if (!names.length) return src;
    names.sort((a, b) => b.length - a.length);

    let out = src;
    names.forEach((name) => {
      if (out.indexOf(name) >= 0) return;
      const L = name.length;
      if (L < 3) return;
      for (let i = 0; i + L <= out.length; i++) {
        const seg = out.substr(i, L);
        if (/[，。！？、,.!?\s]/.test(seg)) continue;
        if (this.editDistance(seg, name) === 1) {
          out = out.slice(0, i) + name + out.slice(i + L);
          break;
        }
      }
    });
    return out;
  },

  /** 把扁平菜单按分类顺序分组（保持后端返回的分类次序） */
  groupByCategory(groups) {
    return groups || [];
  }
};

module.exports = util;
