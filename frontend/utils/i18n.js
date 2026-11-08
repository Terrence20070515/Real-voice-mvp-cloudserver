// utils/i18n.js
// 极简 i18n：语言包 + 读写偏好。四页共用同一份 key（rv_lang）。
// 约定：菜名、分类名保持中文原文（专有名词），只翻界面文案。

const KEY = 'rv_lang';

const PACK = {
  zh: {
    langBtn: 'EN',

    // ── 点单页 ──
    hold: '按住 说话',
    release: '松开 发送',
    listening: '正在聆听，请说出想点的菜…松手后自动发送文字',
    placeholder: '发消息...',
    add: '加',
    assistantTitle: 'AI 点餐助手',
    goCheckout: '去结账 ›',
    todaysMenu: '今日菜单',
    noDishes: '暂无菜品数据',
    emptyBadge: '空',
    ttsOn: '语音播报已开启',
    ttsOff: '语音播报已关闭',
    tooShort: '说话时间太短',
    recognizing: '识别中…',
    noSpeech: '未识别到内容，请重试',
    asrFail: '语音识别失败',
    micPermTitle: '需要麦克风权限',
    micPermBody: '请在设置中开启麦克风权限后使用语音点菜',
    micPermConfirm: '去设置',
    noReply: '（AI 没有返回内容，请重试）',
    netHint: '网络开小差了',
    netHintTimeout: 'AI 思考太久啦，请稍后再试',
    netHintConn: '无法连接后端服务\n\n请检查：\n1. 后端是否已启动（python main.py）\n2. config.js 里的 apiBaseUrl 是否正确（真机用局域网 IP）\n3. 手机和电脑是否在同一个 WiFi',
    addOne: '来一份',

    // ── 首页 ──
    startOrder: '开始 AI 点单',
    startOrderDesc: '说出你想吃什么，剩下的交给它',
    menuHeading: '菜单',
    all: '全部',
    menuNotImported: '菜单尚未导入',
    menuNotImportedSub: '请先到店家后台导入菜单',
    catEmpty: '该分类暂无菜品',
    myOrders: '我的订单',
    about: '关于',
    aboutBody: '本小程序由 AI 助手提供智能点餐服务，告诉它你想吃什么，剩下的交给它。',
    aboutConfirm: '知道了',
    dishUnit: '道菜',
    catUnit: '个分类',
    menuNotLoaded: '菜单未加载',
    loadMenuFail: '加载菜单失败',
    defaultShop: '本店',

    // ── 菜单页 ──
    back: '‹ 返回',
    fullMenu: '完整菜单',
    loadingMenu: '正在加载菜单...',
    notice: '提示',
    menuEmpty: '菜单为空',
    loadFail: '加载失败',
    cart: '购物车',
    noItems: '未选购商品',
    pickDishes: '从菜单选择菜品',
    goOrder: '去下单',
    selected: '已选商品',
    clear: '清空',
    cartEmpty: '购物车空空如也',
    clearCartTitle: '清空购物车',
    clearCartBody: '确定要清空购物车吗？',
    confirm: '确定',
    cancel: '取消',
    orderPrefix: '我要点：',

    // ── 买家页 ──
    payTitle: '买单',
    paySuccess: '支付成功',
    queryingOrders: '正在查询订单...',
    noOrders: '还没有订单',
    noOrdersTip: '去 AI 点餐页面下个单试试',
    goOrdering: '去点餐',
    orderList: '订单列表',
    orderNo: '订单号',
    paid: '✓ 已支付',
    unpaid: '待支付',
    customer: '客户/桌号：',
    totalLabel: '合计',
    paying: '支付中...',
    payNow: '立即支付 ¥',
    paidStamp: '已支付 · 感谢惠顾',
    footerTip: '这是 MVP 演示，支付为模拟，不会真实扣款',
    queryOrdersFail: '查询订单失败',
    payFail: '支付失败',

    // ── 辣度 ──
    spicy: { 微辣: '微辣', 中辣: '中辣', 麻辣: '麻辣', 特辣: '特辣', 不辣: '不辣' }
  },

  en: {
    langBtn: '中',

    // ── Chat ──
    hold: 'Hold to talk',
    release: 'Release to send',
    listening: 'Listening… release to send as text',
    placeholder: 'Message…',
    add: 'Add',
    assistantTitle: 'AI Ordering',
    goCheckout: 'Checkout ›',
    todaysMenu: "Today's menu",
    noDishes: 'No dishes available',
    emptyBadge: 'None',
    ttsOn: 'Voice playback on',
    ttsOff: 'Voice playback off',
    tooShort: 'Too short — hold a bit longer',
    recognizing: 'Recognizing…',
    noSpeech: "Didn't catch that, please try again",
    asrFail: 'Speech recognition failed',
    micPermTitle: 'Microphone access needed',
    micPermBody: 'Enable microphone access in Settings to order by voice',
    micPermConfirm: 'Settings',
    noReply: '(No response from the assistant, please try again)',
    netHint: 'Connection problem',
    netHintTimeout: 'The assistant is taking too long, please try again',
    netHintConn: 'Cannot reach the backend.\n\nPlease check:\n1. Is the backend running (python main.py)?\n2. Is apiBaseUrl in config.js correct (use the LAN IP on a real device)?\n3. Are the phone and computer on the same Wi-Fi?',
    addOne: 'One ',

    // ── Home ──
    startOrder: 'Start AI ordering',
    startOrderDesc: 'Just say what you feel like — it handles the rest',
    menuHeading: 'Menu',
    all: 'All',
    menuNotImported: 'No menu yet',
    menuNotImportedSub: 'Import a menu from the admin panel first',
    catEmpty: 'No dishes in this category',
    myOrders: 'My orders',
    about: 'About',
    aboutBody: 'This mini program is an AI ordering assistant. Tell it what you would like and it handles the rest.',
    aboutConfirm: 'Got it',
    dishUnit: 'dishes',
    catUnit: 'categories',
    menuNotLoaded: 'Menu not loaded',
    loadMenuFail: 'Failed to load the menu',
    defaultShop: 'This restaurant',

    // ── Menu ──
    back: '‹ Back',
    fullMenu: 'Full menu',
    loadingMenu: 'Loading menu…',
    notice: 'Notice',
    menuEmpty: 'The menu is empty',
    loadFail: 'Failed to load',
    cart: 'Cart',
    noItems: 'No items yet',
    pickDishes: 'Pick dishes from the menu',
    goOrder: 'Order',
    selected: 'Selected',
    clear: 'Clear',
    cartEmpty: 'Your cart is empty',
    clearCartTitle: 'Clear cart',
    clearCartBody: 'Clear all selected dishes?',
    confirm: 'Clear',
    cancel: 'Cancel',
    orderPrefix: "I'd like: ",

    // ── Pay ──
    payTitle: 'Checkout',
    paySuccess: 'Payment complete',
    queryingOrders: 'Loading orders…',
    noOrders: 'No orders yet',
    noOrdersTip: 'Order something from the AI chat first',
    goOrdering: 'Order now',
    orderList: 'Orders',
    orderNo: 'Order',
    paid: '✓ Paid',
    unpaid: 'Unpaid',
    customer: 'Guest / table: ',
    totalLabel: 'Total',
    paying: 'Paying…',
    payNow: 'Pay ¥',
    paidStamp: 'Paid · Thank you',
    footerTip: 'MVP demo — payments are simulated and no money is charged',
    queryOrdersFail: 'Failed to load orders',
    payFail: 'Payment failed',

    // ── Spiciness ──
    spicy: { 微辣: 'Mild', 中辣: 'Medium', 麻辣: 'Hot', 特辣: 'Extra hot', 不辣: 'Not spicy' }
  }
};

function normalize(lang) {
  return lang === 'en' ? 'en' : 'zh';
}

/** 当前语言（默认中文） */
function current() {
  try {
    return normalize(wx.getStorageSync(KEY));
  } catch (e) {
    return 'zh';
  }
}

/** 写入语言并返回规范化后的值 */
function set(lang) {
  const l = normalize(lang);
  try {
    wx.setStorageSync(KEY, l);
  } catch (e) {}
  return l;
}

/** 在两种语言间切换 */
function toggle() {
  return set(current() === 'zh' ? 'en' : 'zh');
}

/** 取整包文案，供页面 setData({ i18n: pack(lang) }) */
function pack(lang) {
  return PACK[normalize(lang)];
}

/** 辣度文案；英文下译成 Mild / Medium / Hot，未知值原样返回 */
function spicyText(value, lang) {
  if (!value) return '';
  const table = PACK[normalize(lang)].spicy;
  return table[value] || value;
}

module.exports = { KEY, current, set, toggle, pack, normalize, spicyText };
