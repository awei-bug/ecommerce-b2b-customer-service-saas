import axios from '../utils/requests.js'
import base from './base.js'

const u = (path) => base.baseURL + path

const api = {
  // auth
  change_password(data) {
    return axios.post(u('/user/change-password/'), data)
  },
  agent_ops(data) {
    return axios.post(u('/api/agents/ops/'), data)
  },
  agent_product_content(data) {
    return axios.post(u('/api/agents/product-content/'), data)
  },
  agent_task_logs(params) {
    return axios.get(u('/api/agents/task-logs/'), { params })
  },
  login(params) {
    return axios.post(u(base.login), params)
  },
  me() {
    return axios.get(u(base.me))
  },

  // users
  get_user_list(config) {
    return axios.get(u(base.users), config)
  },
  get_user_by_id(id) {
    return axios.get(u(base.user + id + '/'))
  },
  add_user(data) {
    return axios.post(u(base.users), data)
  },
  edit_user(id, data) {
    return axios.put(u(base.user + id + '/'), data)
  },
  delete_user(id) {
    return axios.delete(u(base.user + id + '/'))
  },
  reset_user_password(id) {
    return axios.post(u(base.resetPwd + id + '/reset_pwd/'))
  },

  // shop
  get_shop_settings() {
    return axios.get(u(base.shopSettings))
  },
  update_shop_settings(data) {
    return axios.put(u(base.shopSettings), data)
  },

  // products
  get_product_list(name) {
    const params = name ? { name } : {}
    return axios.get(u(base.products), { params })
  },
  add_product(data) {
    return axios.post(u(base.products), data)
  },
  update_product(id, data) {
    return axios.put(u(base.product + id + '/'), data)
  },
  delete_product(id) {
    return axios.delete(u(base.product + id + '/'))
  },
  set_product_state(id, state) {
    return axios.post(u(base.product + id + '/state/'), { state })
  },
  list_skus(pid) {
    return axios.get(u(base.product + pid + '/skus/'))
  },
  create_sku(pid, data) {
    return axios.post(u(base.product + pid + '/skus/'), data)
  },
  update_sku(pid, sid, data) {
    return axios.put(u(base.product + pid + '/skus/' + sid + '/'), data)
  },
  delete_sku(pid, sid) {
    return axios.delete(u(base.product + pid + '/skus/' + sid + '/'))
  },
  batch_stock(items) {
    return axios.post(u(base.products + 'stock/batch/'), { items })
  },
  batch_product_covers(items) {
    return axios.post(u(base.products + 'covers/batch/'), { items })
  },
  import_product_pack(file) {
    const fd = new FormData()
    fd.append('file', file)
    return axios.post(u(base.products + 'import-pack/'), fd, { timeout: 120000 })
  },
  download_listing_pack_sample() {
    return axios.get(u(base.products + 'import-pack/sample/'), {
      responseType: 'blob',
      timeout: 30000,
    })
  },

  // category / attr
  get_category(level) {
    return axios.get(u(base.categorys), { params: { level } })
  },
  add_category(data) {
    return axios.post(u(base.categorys), data)
  },
  get_attr_by_category(cid, _type) {
    return axios.get(u(base.attributes), { params: { cid, _type } })
  },
  add_attribute(data) {
    return axios.post(u(base.attributes), data)
  },
  update_attr_value(id, data) {
    return axios.put(u(base.attribute + id + '/'), data)
  },

  // orders
  get_orders(params) {
    return axios.get(u(base.orders), { params })
  },
  get_order(id) {
    return axios.get(u(base.order + id + '/'))
  },
  create_order(data) {
    return axios.post(u(base.orders), data)
  },
  cancel_order(id, data) {
    return axios.post(u(base.order + id + '/cancel/'), data || {})
  },
  mark_order_paid(id, data) {
    return axios.post(u(base.order + id + '/mark-paid/'), data || {})
  },
  ship_order(id, data) {
    return axios.post(u(base.order + id + '/ship/'), data || {})
  },
  complete_order(id) {
    return axios.post(u(base.order + id + '/complete/'))
  },
  refund_apply(id) {
    return axios.post(u(base.order + id + '/refund/apply/'))
  },
  refund_approve(id, data) {
    return axios.post(u(base.order + id + '/refund/approve/'), data || {})
  },
  refund_reject(id) {
    return axios.post(u(base.order + id + '/refund/reject/'))
  },
  get_express(id) {
    return axios.get(u(base.expresses + id + '/'))
  },
  export_orders(params) {
    return axios.get(u(base.ordersExport), { params, responseType: 'blob' })
  },
  export_payments(params) {
    return axios.get(u(base.paymentsExport), { params, responseType: 'blob' })
  },
  orders_summary() {
    return axios.get(u(base.ordersSummary))
  },
  dashboard_kpi() {
    return axios.get(u(base.dashboardKpi))
  },

  // customer service center
  support_inbox(params) {
    return axios.get(u('/api/agents/support/inbox/'), { params })
  },
  support_conversation(id) {
    return axios.get(u('/api/agents/support/conversations/' + id + '/'))
  },
  support_claim(id) {
    return axios.post(u('/api/agents/support/conversations/' + id + '/claim/'))
  },
  support_reply(id, content) {
    return axios.post(u('/api/agents/support/conversations/' + id + '/reply/'), { content })
  },
  support_resolve(id) {
    return axios.post(u('/api/agents/support/conversations/' + id + '/resolve/'))
  },
  support_priority(id, priority) {
    return axios.put(u('/api/agents/support/conversations/' + id + '/priority/'), { priority })
  },
  store_knowledge(params) {
    return axios.get(u('/api/agents/knowledge/'), { params })
  },
  create_store_knowledge(data) {
    return axios.post(u('/api/agents/knowledge/'), data)
  },
  update_store_knowledge(id, data) {
    return axios.put(u('/api/agents/knowledge/' + id + '/'), data)
  },
  delete_store_knowledge(id) {
    return axios.delete(u('/api/agents/knowledge/' + id + '/'))
  },
  import_store_knowledge(file) {
    const form = new FormData()
    form.append('file', file)
    return axios.post(u('/api/agents/knowledge/import/'), form, { timeout: 60000 })
  },
  download_store_knowledge_template() {
    return axios.get(u('/api/agents/knowledge/template/'), { responseType: 'blob' })
  },

  // AI automation center
  automation_overview(params) {
    return axios.get(u('/api/automation/overview/'), { params })
  },
  automation_rules() {
    return axios.get(u('/api/automation/rules/'))
  },
  update_automation_rule(id, data) {
    return axios.put(u('/api/automation/rules/' + id + '/'), data)
  },
  run_automation_rule(id) {
    return axios.post(u('/api/automation/rules/' + id + '/run/'))
  },
  save_ad_campaign(data) {
    return axios.post(u('/api/automation/campaigns/'), data)
  },
  automation_competitors() {
    return axios.get(u('/api/automation/competitors/'))
  },
  create_automation_competitor(data) {
    return axios.post(u('/api/automation/competitors/'), data)
  },
  scan_automation_competitor(id, data) {
    return axios.post(u('/api/automation/competitors/' + id + '/scan/'), data || {})
  },
  generate_creative_kit(data) {
    return axios.post(u('/api/automation/creative/generate/'), data)
  },
  apply_creative_image(data) {
    return axios.post(u('/api/automation/creative/apply/'), data)
  },
  start_creative_auto(data) {
    return axios.post(u('/api/automation/creative/auto/start/'), data)
  },
  creative_auto_status(id) {
    return axios.get(u('/api/automation/creative/auto/' + id + '/'))
  },
  creative_auto_current() {
    return axios.get(u('/api/automation/creative/auto/current/'))
  },
  stop_creative_auto(id) {
    return axios.post(u('/api/automation/creative/auto/' + id + '/stop/'))
  },
  inspect_creative(data) {
    return axios.post(u('/api/automation/creative/inspect/'), data)
  },
  agnes_image(data) {
    return axios.post(u('/api/agents/media/image/'), data, { timeout: 360000 })
  },
  agnes_video_create(data) {
    return axios.post(u('/api/agents/media/video/'), data, { timeout: 90000 })
  },
  agnes_video_status(videoId) {
    return axios.get(u('/api/agents/media/video/' + encodeURIComponent(videoId) + '/'), { timeout: 30000 })
  },

  // pay
  pay_create(data) {
    return axios.post(u(base.pay + '/create/'), data)
  },
  pay_mock_notify(data) {
    return axios.post(u(base.pay + '/mock/notify/'), data)
  },
  pay_channel_status() {
    return axios.get(u(base.pay + '/channel/status/'))
  },

  // menu / role
  get_menu_list() {
    return axios.get(u(base.menus))
  },
  get_menu() {
    return axios.get(u(base.menus), { params: { type_: 'tree' } })
  },
  get_roles() {
    return axios.get(u(base.roles))
  },
  update_role(id, data) {
    return axios.put(u(base.role + id + '/'), data)
  },
  set_menu(rid, data) {
    return axios.post(u(base.role + rid + '/'), data)
  },
  del_role_menu(rid, mid) {
    return axios.delete(u(base.role + rid + '/' + mid + '/'))
  },
  get_action_codes() {
    return axios.get(u(base.permissions))
  },

  // freight
  get_freight_templates() {
    return axios.get(u(base.freight))
  },
  create_freight_template(data) {
    return axios.post(u(base.freight), data)
  },
  update_freight_template(id, data) {
    return axios.put(u(base.freight + id + '/'), data)
  },
  delete_freight_template(id) {
    return axios.delete(u(base.freight + id + '/'))
  },

}

export default api
