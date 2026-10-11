<!-- 普通商家只看到自动上架主流程；实验能力保留在底层，待真实数据闭环后再开放。 -->
<template>
  <div class="automation-page" v-loading="loading">
    <header class="page-head">
      <div>
        <div class="title-line">
          <h1>AI 自动上架</h1>
          <span class="live-badge"><i></i>商品数据已连接</span>
        </div>
        <p>自动生成商品内容与主图，保存后直接同步到商城前台。</p>
      </div>
      <div class="head-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadCreativeWorkspace">刷新商品</el-button>
      </div>
    </header>

    <div v-if="false" class="source-bar">
      <span>统计区间 {{ period.start || '--' }} 至 {{ period.end || '--' }}</span>
      <span class="source-item"><i class="ok"></i>订单</span>
      <span class="source-item"><i class="ok"></i>支付</span>
      <span class="source-item"><i class="ok"></i>退款</span>
      <span class="source-item"><i :class="finance.source_status?.ads === 'connected' ? 'ok' : 'warn'"></i>广告{{ finance.source_status?.ads === 'connected' ? '' : '未接入' }}</span>
      <span class="generated">更新于 {{ generatedAt || '--' }}</span>
    </div>

    <nav v-if="false" class="workspace-nav" aria-label="自动化中心工作区">
      <button v-for="item in tabs" :key="item.value" type="button" :class="{ active: activeTab === item.value }" @click="activeTab = item.value">
        <el-icon><component :is="item.icon" /></el-icon>{{ item.label }}
      </button>
    </nav>

    <section v-if="false && activeTab === 'cockpit'" class="workspace">
      <div class="metric-strip">
        <div class="metric-cell">
          <span>成交收入</span>
          <strong>{{ money(finance.kpi?.revenue) }}</strong>
          <small>{{ finance.extra?.order_count || 0 }} 笔已支付订单</small>
        </div>
        <div class="metric-cell">
          <span>经营利润</span>
          <strong :class="tone(finance.kpi?.operating_profit)">{{ money(finance.kpi?.operating_profit) }}</strong>
          <small>{{ finance.assumptions?.cost_rate_label || '估算成本率 55%' }}</small>
        </div>
        <div class="metric-cell">
          <span>广告 ROAS</span>
          <strong>{{ ratio(finance.kpi?.roas) }}</strong>
          <small>{{ finance.kpi?.roas == null ? '录入广告数据后计算' : '归因成交 / 广告消耗' }}</small>
        </div>
        <div class="metric-cell">
          <span>自动化健康度</span>
          <strong>{{ automation.success_rate == null ? '--' : automation.success_rate + '%' }}</strong>
          <small>{{ automation.enabled || 0 }} / {{ automation.total || 0 }} 条规则运行中</small>
        </div>
      </div>

      <div class="overview-grid">
        <section class="insight-panel" aria-labelledby="insight-title">
          <div class="section-head">
            <div><h2 id="insight-title">经营诊断</h2><p>按利润、投放、退款和现金流自动排优先级</p></div>
            <el-button link type="primary" @click="activeTab = 'finance'">查看三大报表</el-button>
          </div>
          <div class="insight-list">
            <div v-for="item in finance.recommendations || []" :key="item.title" class="insight-row">
              <span class="severity" :class="item.level"><el-icon><Warning v-if="item.level !== 'success'" /><CircleCheck v-else /></el-icon></span>
              <div><strong>{{ item.title }}</strong><p>{{ item.detail }}</p></div>
              <el-button size="small" @click="routeInsight(item.action)">{{ item.action }}</el-button>
            </div>
          </div>
        </section>

        <aside class="run-panel">
          <div class="section-head"><div><h2>最近执行</h2><p>状态、耗时结果与失败入口</p></div><el-button link type="primary" @click="activeTab = 'workflows'">全部流程</el-button></div>
          <div v-if="automation.recent_runs?.length" class="run-list">
            <div v-for="run in automation.recent_runs" :key="run.id" class="run-row">
              <span class="run-dot" :class="run.status"></span>
              <div><strong>{{ moduleName(run.module_code) }}</strong><p>{{ run.summary }}</p></div>
              <time>{{ shortTime(run.finished_at) }}</time>
            </div>
          </div>
          <el-empty v-else :image-size="52" description="尚无执行记录，运行一条流程后会显示在这里" />
        </aside>
      </div>

      <section class="modules-section">
        <div class="section-head">
          <div><h2>八大业务模块</h2><p>从数据结论进入业务操作，不停留在数字罗列</p></div>
          <el-button type="primary" :icon="VideoPlay" :loading="runningAll" @click="runAll">运行全部检查</el-button>
        </div>
        <div class="module-grid">
          <button v-for="item in modules" :key="item.code" type="button" class="module-item" @click="openModule(item.code)">
            <span class="module-icon" :class="item.state"><el-icon><component :is="moduleIcon(item.code)" /></el-icon></span>
            <span class="module-copy"><strong>{{ item.name }}</strong><small>{{ item.metric }}</small></span>
            <el-icon class="arrow"><ArrowRight /></el-icon>
          </button>
        </div>
      </section>

      <section class="data-section">
        <div class="section-head"><div><h2>选品机会</h2><p>综合成交、热度、库存和商品完整度排序</p></div><el-button @click="$router.push('/product_list')">进入商品中心</el-button></div>
        <el-table :data="selection" size="small" empty-text="暂无商品数据">
          <el-table-column prop="name" label="商品" min-width="180" show-overflow-tooltip />
          <el-table-column prop="score" label="机会分" width="100"><template #default="{ row }"><strong>{{ row.score }}</strong></template></el-table-column>
          <el-table-column prop="units" label="销量" width="90" />
          <el-table-column label="成交额" width="120"><template #default="{ row }">{{ money(row.revenue) }}</template></el-table-column>
          <el-table-column prop="stock" label="库存" width="90" />
          <el-table-column label="建议" width="110"><template #default="{ row }"><el-tag :type="row.score >= 70 ? 'success' : row.score >= 35 ? 'warning' : 'info'" effect="plain">{{ row.signal }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="makeCreative(row.product_id)">生成素材</el-button></template></el-table-column>
        </el-table>
      </section>
    </section>

    <section v-else-if="false && activeTab === 'finance'" class="workspace">
      <div class="section-head finance-heading">
        <div><h2>财务经营分析</h2><p>用利润、资产与现金流交叉定位问题；非会计凭证字段均明确标注估算。</p></div>
        <el-button type="primary" :icon="Plus" @click="campaignDialog = true">录入广告日数据</el-button>
      </div>
      <div class="report-grid">
        <section v-for="report in reports" :key="report.key" class="report-sheet">
          <div class="report-title"><span>{{ report.name }}</span><small>{{ report.help }}</small></div>
          <div v-for="row in finance[report.key] || []" :key="row.label" class="report-row" :class="row.kind">
            <span>{{ row.label }}</span><strong>{{ money(row.amount) }}</strong>
          </div>
        </section>
      </div>
      <div class="finance-notice"><el-icon><InfoFilled /></el-icon><span>当前商品模型没有采购成本字段，利润表使用 {{ finance.assumptions?.cost_rate_label || '估算成本率' }}。接入 ERP 成本后可替换为实际移动加权成本。</span></div>
      <section class="data-section">
        <div class="section-head"><div><h2>广告 ROI 台账</h2><p>支持人工录入；接入平台连接器后仍落入同一标准数据表</p></div></div>
        <el-table :data="finance.campaigns || []" size="small" empty-text="尚无广告数据，点击“录入广告日数据”开始">
          <el-table-column prop="record_date" label="日期" width="110" />
          <el-table-column prop="platform" label="平台" width="100" />
          <el-table-column prop="campaign_name" label="计划" min-width="180" />
          <el-table-column label="消耗" width="110"><template #default="{ row }">{{ money(row.spend) }}</template></el-table-column>
          <el-table-column label="归因成交" width="120"><template #default="{ row }">{{ money(row.revenue) }}</template></el-table-column>
          <el-table-column prop="orders" label="订单" width="80" />
          <el-table-column label="ROAS" width="90"><template #default="{ row }"><strong :class="row.roas != null && row.roas < 2 ? 'negative' : 'positive'">{{ ratio(row.roas) }}</strong></template></el-table-column>
          <el-table-column label="来源" width="100"><template #default="{ row }"><el-tag size="small" effect="plain">{{ row.source === 'manual' ? '人工录入' : row.source }}</el-tag></template></el-table-column>
        </el-table>
      </section>
    </section>

    <section v-else-if="false && activeTab === 'workflows'" class="workspace">
      <div class="section-head finance-heading">
        <div><h2>自动化流程</h2><p>启停、立即运行并查看结果；调价、下架、退款和投放变更仍需人工确认。</p></div>
        <el-button type="primary" :icon="VideoPlay" :loading="runningAll" @click="runAll">运行全部检查</el-button>
      </div>
      <div class="workflow-summary">
        <span><strong>{{ automation.enabled || 0 }}</strong> 运行中</span>
        <span><strong>{{ automation.total || 0 }}</strong> 总流程</span>
        <span><strong>{{ automation.success_rate == null ? '--' : automation.success_rate + '%' }}</strong> 成功率</span>
        <span class="guard"><el-icon><Lock /></el-icon>高风险动作已开启人工确认</span>
      </div>
      <el-table :data="rules" class="workflow-table" empty-text="暂无自动化规则">
        <el-table-column label="状态" width="78"><template #default="{ row }"><el-switch :model-value="row.status === 'enabled'" :loading="row._saving" @change="toggleRule(row, $event)" /></template></el-table-column>
        <el-table-column label="流程" min-width="210"><template #default="{ row }"><div class="rule-name"><span class="module-icon compact" :class="row.status === 'enabled' ? 'ready' : ''"><el-icon><component :is="moduleIcon(row.module_code)" /></el-icon></span><div><strong>{{ row.name }}</strong><small>{{ moduleName(row.module_code) }}</small></div></div></template></el-table-column>
        <el-table-column prop="trigger_type" label="触发" width="100"><template #default="{ row }">{{ row.trigger_type === 'schedule' ? '定时' : row.trigger_type }}</template></el-table-column>
        <el-table-column prop="schedule" label="执行计划" min-width="130" />
        <el-table-column label="最近执行" min-width="160"><template #default="{ row }">{{ row.last_run_at ? shortTime(row.last_run_at) : '从未执行' }}</template></el-table-column>
        <el-table-column label="成功/总计" width="100"><template #default="{ row }">{{ row.success_count }}/{{ row.run_count }}</template></el-table-column>
        <el-table-column label="操作" width="110" fixed="right"><template #default="{ row }"><el-button link type="primary" :loading="row._running" @click="runRule(row)">立即运行</el-button></template></el-table-column>
      </el-table>
    </section>

    <section v-else-if="false && activeTab === 'market'" class="workspace">
      <div class="section-head finance-heading">
        <div><h2>竞品与售后监控</h2><p>竞品价格、排名、活动、评论异常与售后问题分类统一进入预警队列。</p></div>
        <el-radio-group v-model="marketMode" size="small">
          <el-radio-button value="competitor">竞品监控</el-radio-button>
          <el-radio-button value="aftersale">售后分类</el-radio-button>
        </el-radio-group>
      </div>
      <template v-if="marketMode === 'competitor'">
        <div class="toolbar-line"><span>{{ competitors.length }} 个监控目标</span><el-button type="primary" :icon="Plus" @click="competitorDialog = true">添加竞品</el-button></div>
        <el-table :data="competitors" empty-text="尚无竞品监控目标">
          <el-table-column prop="competitor_name" label="竞品" min-width="160" />
          <el-table-column prop="platform" label="平台" width="100" />
          <el-table-column label="价格" width="120"><template #default="{ row }"><span>{{ money(row.current_price) }}</span><small v-if="row.price_change" :class="row.price_change < 0 ? 'negative' : 'positive'"> {{ row.price_change > 0 ? '+' : '' }}{{ row.price_change }}</small></template></el-table-column>
          <el-table-column prop="rank" label="排名" width="80"><template #default="{ row }">{{ row.rank || '--' }}</template></el-table-column>
          <el-table-column prop="activity" label="活动" min-width="130"><template #default="{ row }">{{ row.activity || '--' }}</template></el-table-column>
          <el-table-column label="异常" min-width="180"><template #default="{ row }"><span v-if="!row.alert_flags?.length" class="quiet">正常</span><el-tag v-for="flag in row.alert_flags" :key="flag" type="warning" size="small" effect="plain" class="flag">{{ flag }}</el-tag></template></el-table-column>
          <el-table-column label="检查时间" width="150"><template #default="{ row }">{{ shortTime(row.last_checked_at) }}</template></el-table-column>
          <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="scanCompetitor(row)">更新快照</el-button></template></el-table-column>
        </el-table>
      </template>
      <template v-else>
        <div class="aftersale-summary">
          <div><strong>{{ afterSales.total || 0 }}</strong><span>问题订单</span></div>
          <div v-for="item in afterSales.categories || []" :key="item.name"><strong>{{ item.count }}</strong><span>{{ item.name }} · {{ item.ratio }}%</span></div>
        </div>
        <el-table :data="afterSales.cases || []" empty-text="当前区间没有售后问题单">
          <el-table-column prop="order_no" label="订单号" min-width="150" />
          <el-table-column label="金额" width="110"><template #default="{ row }">{{ money(row.amount) }}</template></el-table-column>
          <el-table-column prop="category" label="自动分类" width="120"><template #default="{ row }"><el-tag effect="plain">{{ row.category }}</el-tag></template></el-table-column>
          <el-table-column prop="reason" label="原始原因" min-width="200" show-overflow-tooltip />
          <el-table-column prop="route" label="处理路径" width="110" />
          <el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" @click="$router.push('/order_list?order_no=' + row.order_no)">处理订单</el-button></template></el-table-column>
        </el-table>
      </template>
    </section>

    <section v-else class="workspace creative-workspace">
      <section class="auto-listing-panel">
        <div class="auto-listing-copy">
          <div class="auto-listing-title"><el-icon><VideoPlay /></el-icon><h3>一键自动上架</h3><el-tag v-if="creativeAutoRun" :type="autoRunTone" effect="plain">{{ autoRunLabel }}</el-tag></div>
          <p>点击开始后，系统会依次生成内容、主图、保存资源并上架；运行中可以随时结束。</p>
          <div v-if="creativeAutoRun" class="auto-progress"><el-progress :percentage="autoRunProgress" :status="autoRunProgressStatus" /><span>{{ creativeAutoRun.summary || '任务处理中' }}</span></div>
          <div v-if="creativeAutoRun?.output?.results?.length" class="auto-result-list">
            <span v-for="item in creativeAutoRun.output.results.slice(-5)" :key="item.product_id" :class="item.status === 'success' ? 'ok' : 'bad'">{{ item.name }}：{{ item.status === 'success' ? '已上架' : item.error || '失败' }}</span>
          </div>
        </div>
        <div class="auto-listing-controls">
          <el-button v-if="!creativeAutoRun || ['success', 'partial', 'failed', 'stopped'].includes(creativeAutoRun.status)" type="primary" :loading="creativeAutoStarting" @click="startCreativeAuto">开始</el-button>
          <el-button v-else type="danger" plain :loading="creativeAutoStopping" @click="stopCreativeAuto">结束</el-button>
        </div>
      </section>
      <details class="advanced-tools">
        <summary>高级模式：指定商品、渠道与图片质检</summary>
        <div class="advanced-scope">
          <span>自动处理范围</span>
          <el-select v-model="creativeAutoScope" size="small" :disabled="!!creativeAutoRun && ['running', 'stopping'].includes(creativeAutoRun.status)" style="width:190px"><el-option v-if="isDemoTenant" label="自动创建新商品（演示）" value="create_new" /><el-option label="仅处理缺主图" value="missing_image" /><el-option label="处理全部商品" value="all_products" /></el-select>
        </div>
        <div class="creative-grid">
        <section class="creative-form">
          <h3>商品素材方案</h3>
          <el-form label-position="top">
            <el-form-item label="商品">
              <el-select v-model="creativeForm.product_id" filterable placeholder="选择商品" style="width:100%">
                <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标渠道">
              <el-select v-model="creativeForm.channel" style="width:100%"><el-option v-for="c in ['通用电商', '淘宝', '京东', '抖音商城', '小红书']" :key="c" :label="c" :value="c" /></el-select>
            </el-form-item>
            <el-form-item label="同时生成主图">
              <el-switch v-model="creativeForm.with_image" active-text="Agnes 图片模型" />
            </el-form-item>
            <el-button type="primary" :loading="creativeLoading" :disabled="!creativeForm.product_id" @click="generateCreative">生成素材方案</el-button>
          </el-form>
          <div class="form-divider"></div>
          <h3>图片尺寸质检</h3>
          <el-form label-position="top">
            <div class="dimension-row"><el-form-item label="原图宽"><el-input-number v-model="inspectForm.width" :min="0" controls-position="right" /></el-form-item><el-form-item label="原图高"><el-input-number v-model="inspectForm.height" :min="0" controls-position="right" /></el-form-item></div>
            <div class="dimension-row"><el-form-item label="目标宽"><el-input-number v-model="inspectForm.target_width" :min="1" controls-position="right" /></el-form-item><el-form-item label="目标高"><el-input-number v-model="inspectForm.target_height" :min="1" controls-position="right" /></el-form-item></div>
            <el-button :loading="inspectLoading" @click="inspectCreative">开始质检</el-button>
          </el-form>
        </section>
        <section class="creative-output">
          <template v-if="creativeKit">
            <div class="output-head"><div><span>生成结果</span><h3>{{ creativeKit.title }}</h3></div><el-tag :type="creativeKit.status === 'ready' ? 'success' : 'warning'" effect="plain">{{ creativeKit.status === 'ready' ? '可交付' : '需补源素材' }}</el-tag></div>
            <div class="brief-block"><strong>主图 Brief</strong><p>{{ creativeKit.main_image_brief }}</p></div>
            <div v-if="creativeKit.image?.url" class="generated-media">
              <strong>Agnes 生成主图</strong>
              <el-image :src="creativeKit.image.url" fit="contain" :preview-src-list="[creativeKit.image.url]" class="generated-image" />
              <small>{{ creativeKit.image.model }}</small>
              <div class="creative-apply-bar">
                <el-switch v-model="creativePublish" active-text="确认后同步上架" />
                <el-button type="success" :loading="creativeApplying" @click="applyCreativeImage">保存到商品</el-button>
              </div>
              <small class="apply-hint">图片会先保存到本店资源目录；勾选上架后，商城前台立即使用这张主图。</small>
            </div>
            <div class="size-plan"><div v-for="size in creativeKit.size_plan" :key="size.usage"><span>{{ size.usage }}</span><strong>{{ size.width }} × {{ size.height }}</strong></div></div>
            <div class="detail-plan"><div v-for="part in creativeKit.detail_sections" :key="part.title"><strong>{{ part.title }}</strong><ul><li v-for="line in part.content" :key="line">{{ line }}</li></ul></div></div>
            <el-alert v-if="creativeKit.issues?.length" type="warning" :closable="false" show-icon :title="'待补齐：' + creativeKit.issues.join('、')" />
            <p class="connector-note">{{ creativeKit.notice }}</p>
          </template>
          <template v-else-if="inspectResult">
            <el-result :icon="inspectResult.passed ? 'success' : 'warning'" :title="inspectResult.passed ? '尺寸质检通过' : '发现素材问题'" :sub-title="`建议输出 ${inspectResult.output.target_width} × ${inspectResult.output.target_height}，处理方式：${inspectResult.output.mode === 'center_crop' ? '居中裁切' : '等比缩放'}`">
              <template #extra><div v-for="issue in inspectResult.issues" :key="issue.code" class="issue-line">{{ issue.message }}</div></template>
            </el-result>
          </template>
          <el-empty v-else description="选择商品生成方案，或输入图片尺寸开始质检" />
        </section>
        </div>
      </details>
    </section>

    <el-dialog v-model="campaignDialog" title="录入广告日数据" width="560px" destroy-on-close>
      <el-form label-position="top">
        <div class="dialog-grid"><el-form-item label="日期"><el-date-picker v-model="campaignForm.record_date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="平台"><el-select v-model="campaignForm.platform" style="width:100%"><el-option v-for="p in ['douyin', 'tmall', 'jd', 'xiaohongshu', 'manual']" :key="p" :label="p" :value="p" /></el-select></el-form-item></div>
        <el-form-item label="广告计划"><el-input v-model="campaignForm.campaign_name" placeholder="例如：秋季新品-核心人群" /></el-form-item>
        <div class="dialog-grid"><el-form-item label="消耗"><el-input-number v-model="campaignForm.spend" :min="0" :precision="2" controls-position="right" /></el-form-item><el-form-item label="归因成交"><el-input-number v-model="campaignForm.revenue" :min="0" :precision="2" controls-position="right" /></el-form-item><el-form-item label="归因订单"><el-input-number v-model="campaignForm.orders" :min="0" controls-position="right" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="campaignDialog = false">取消</el-button><el-button type="primary" :loading="savingCampaign" @click="saveCampaign">保存并重算</el-button></template>
    </el-dialog>

    <el-dialog v-model="competitorDialog" title="添加竞品监控" width="560px" destroy-on-close>
      <el-form label-position="top">
        <div class="dialog-grid"><el-form-item label="竞品名称"><el-input v-model="competitorForm.competitor_name" /></el-form-item><el-form-item label="平台"><el-input v-model="competitorForm.platform" placeholder="淘宝 / 京东 / 抖音" /></el-form-item></div>
        <el-form-item label="商品链接"><el-input v-model="competitorForm.source_url" placeholder="可选；接入平台连接器后自动抓取" /></el-form-item>
        <div class="dialog-grid"><el-form-item label="当前价格"><el-input-number v-model="competitorForm.current_price" :min="0" :precision="2" controls-position="right" /></el-form-item><el-form-item label="当前排名"><el-input-number v-model="competitorForm.rank" :min="1" controls-position="right" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="competitorDialog = false">取消</el-button><el-button type="primary" :loading="savingCompetitor" @click="saveCompetitor">开始监控</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, markRaw, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight, Brush, CircleCheck, Coin, Connection, DataAnalysis, DocumentChecked,
  Goods, InfoFilled, Lock, MagicStick, Plus, Refresh, Service, ShoppingCart,
  TrendCharts, VideoPlay, Warning,
} from '@element-plus/icons-vue'
import api from '@/api/index.js'

const router = useRouter()
const loading = ref(false)
const runningAll = ref(false)
const days = ref(30)
const activeTab = ref('creative')
const marketMode = ref('competitor')
const overview = ref({})
const rules = ref([])
const competitors = ref([])
const products = ref([])
const generatedAt = ref('')

const campaignDialog = ref(false)
const competitorDialog = ref(false)
const savingCampaign = ref(false)
const savingCompetitor = ref(false)
const creativeLoading = ref(false)
const inspectLoading = ref(false)
const creativeKit = ref(null)
const creativePublish = ref(false)
const creativeApplying = ref(false)
const creativeAutoRun = ref(null)
const tenant = JSON.parse(sessionStorage.getItem('tenant') || 'null') || {}
const isDemoTenant = tenant.data_mode === 'demo' || tenant.slug === 'demo'
const creativeAutoScope = ref(isDemoTenant ? 'create_new' : 'missing_image')
const creativeAutoStarting = ref(false)
const creativeAutoStopping = ref(false)
let creativeAutoTimer = null
const inspectResult = ref(null)
const videoLoading = ref(false)
const videoPrompt = ref('')
const videoAspect = ref('16:9')
const videoTask = ref(null)
let videoTimer = null

const today = new Date().toISOString().slice(0, 10)
const campaignForm = reactive({ record_date: today, platform: 'douyin', campaign_name: '', spend: 0, revenue: 0, orders: 0 })
const competitorForm = reactive({ competitor_name: '', platform: '淘宝', source_url: '', current_price: 0, rank: null })
const creativeForm = reactive({ product_id: null, channel: '通用电商', with_image: false })
const inspectForm = reactive({ has_image: true, width: 1200, height: 628, target_width: 800, target_height: 800 })

const tabs = [
  { value: 'cockpit', label: '经营驾驶舱', icon: markRaw(DataAnalysis) },
  { value: 'finance', label: '财务与 ROI', icon: markRaw(Coin) },
  { value: 'workflows', label: '自动化流程', icon: markRaw(Connection) },
  { value: 'market', label: '竞品与售后', icon: markRaw(TrendCharts) },
  { value: 'creative', label: '素材自动化', icon: markRaw(Brush) },
]
const reports = [
  { key: 'income_statement', name: '利润表', help: '哪里赚、哪里亏' },
  { key: 'balance_sheet', name: '资产负债表', help: '资金压在哪里' },
  { key: 'cash_flow', name: '现金流量表', help: '现金从哪里进出' },
]
const iconMap = {
  selection: markRaw(TrendCharts), listing: markRaw(Goods), creative: markRaw(MagicStick),
  service: markRaw(Service), aftersale: markRaw(DocumentChecked), finance: markRaw(Coin),
  ads: markRaw(DataAnalysis), competitor: markRaw(ShoppingCart),
}
const nameMap = { selection: '选品调研', listing: '商品上架', creative: '素材自动化', service: '客服质检', aftersale: '售后分类', finance: '利润核算', ads: '广告 ROI', competitor: '竞品监控' }

const finance = computed(() => overview.value.finance || {})
const automation = computed(() => overview.value.automation || {})
const modules = computed(() => overview.value.modules || [])
const selection = computed(() => overview.value.selection || [])
const afterSales = computed(() => overview.value.after_sales || {})
const period = computed(() => overview.value.period || {})
const autoRunProgress = computed(() => {
  const output = creativeAutoRun.value?.output || {}
  const total = Number(output.total || 0)
  return total ? Math.min(100, Math.round(Number(output.completed || 0) / total * 100)) : 0
})
const autoRunProgressStatus = computed(() => creativeAutoRun.value?.status === 'failed' ? 'exception' : undefined)
const autoRunLabel = computed(() => ({ running: '运行中', stopping: '正在结束', success: '已完成', partial: '部分完成', failed: '失败', stopped: '已结束' }[creativeAutoRun.value?.status] || '准备中'))
const autoRunTone = computed(() => ({ running: 'warning', stopping: 'warning', success: 'success', partial: 'warning', failed: 'danger', stopped: 'info' }[creativeAutoRun.value?.status] || 'info'))

function moduleIcon(code) { return iconMap[code] || DataAnalysis }
function moduleName(code) { return nameMap[code] || code }
function money(value) { return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', minimumFractionDigits: 2 }).format(Number(value || 0)) }
function ratio(value) { return value == null ? '--' : Number(value).toFixed(2) }
function tone(value) { return Number(value || 0) < 0 ? 'negative' : 'positive' }
function shortTime(value) { return value ? String(value).replace('T', ' ').slice(0, 16) : '--' }

async function loadOverview() {
  const res = await api.automation_overview({ days: days.value })
  if (res.data.status !== 200) throw new Error(res.data.msg || '经营数据加载失败')
  overview.value = res.data.data || {}
  generatedAt.value = shortTime(overview.value.generated_at)
}
async function loadRules() {
  const res = await api.automation_rules()
  if (res.data.status === 200) rules.value = res.data.data || []
}
async function loadCompetitors() {
  const res = await api.automation_competitors()
  if (res.data.status === 200) competitors.value = res.data.data || []
}
async function loadProducts() {
  const res = await api.get_product_list()
  if (res.data.status === 200) products.value = res.data.data || []
}
async function loadAll() {
  loading.value = true
  try {
    await loadOverview()
    await Promise.all([loadRules(), loadCompetitors(), loadProducts()])
  } catch (error) {
    ElMessage.error(error?.message || '自动化中心加载失败')
  } finally { loading.value = false }
}

async function loadCreativeWorkspace() {
  loading.value = true
  try {
    await Promise.all([loadProducts(), restoreCreativeAutoRun()])
  } catch (error) {
    ElMessage.error(error?.message || '自动上架工作区加载失败')
  } finally {
    loading.value = false
  }
}

function openModule(code) {
  if (['finance', 'ads'].includes(code)) activeTab.value = 'finance'
  else if (['competitor', 'aftersale'].includes(code)) { activeTab.value = 'market'; marketMode.value = code === 'competitor' ? 'competitor' : 'aftersale' }
  else if (code === 'creative') activeTab.value = 'creative'
  else if (code === 'listing') router.push('/product_list')
  else if (code === 'service') router.push('/agent_ops')
  else activeTab.value = 'cockpit'
}
function routeInsight(action) {
  if (action?.includes('广告') || action?.includes('利润')) activeTab.value = 'finance'
  else if (action?.includes('售后')) { activeTab.value = 'market'; marketMode.value = 'aftersale' }
  else activeTab.value = 'workflows'
}
async function toggleRule(row, enabled) {
  row._saving = true
  try {
    const res = await api.update_automation_rule(row.id, { status: enabled ? 'enabled' : 'disabled' })
    if (res.data.status !== 200) throw new Error(res.data.msg)
    Object.assign(row, res.data.data)
    ElMessage.success(enabled ? '流程已启用' : '流程已暂停')
    await loadOverview()
  } catch (error) { ElMessage.error(error?.message || '状态更新失败') } finally { row._saving = false }
}
async function runRule(row, quiet = false) {
  row._running = true
  try {
    const res = await api.run_automation_rule(row.id)
    if (res.data.status !== 200) throw new Error(res.data.msg)
    if (!quiet) ElMessage.success(res.data.msg || '执行完成')
  } catch (error) {
    if (!quiet) ElMessage.error(error?.message || '流程执行失败')
  } finally { row._running = false }
}
async function runAll() {
  runningAll.value = true
  try {
    for (const row of rules.value.filter((x) => x.status === 'enabled')) await runRule(row, true)
    ElMessage.success('全部自动化检查已完成')
    await Promise.all([loadOverview(), loadRules()])
  } finally { runningAll.value = false }
}
async function saveCampaign() {
  if (!campaignForm.campaign_name.trim()) return ElMessage.warning('请填写广告计划名称')
  savingCampaign.value = true
  try {
    const res = await api.save_ad_campaign({ ...campaignForm })
    if (res.data.status !== 200) throw new Error(res.data.msg)
    campaignDialog.value = false
    ElMessage.success('广告数据已保存，ROI 已重算')
    await loadOverview()
  } catch (error) { ElMessage.error(error?.message || '保存失败') } finally { savingCampaign.value = false }
}
async function saveCompetitor() {
  if (!competitorForm.competitor_name.trim()) return ElMessage.warning('请填写竞品名称')
  savingCompetitor.value = true
  try {
    const res = await api.create_automation_competitor({ ...competitorForm })
    if (res.data.status !== 200) throw new Error(res.data.msg)
    competitorDialog.value = false
    ElMessage.success('竞品监控已创建')
    Object.assign(competitorForm, { competitor_name: '', platform: '淘宝', source_url: '', current_price: 0, rank: null })
    await loadCompetitors()
  } catch (error) { ElMessage.error(error?.message || '创建失败') } finally { savingCompetitor.value = false }
}
async function scanCompetitor(row) {
  try {
    const { value } = await ElMessageBox.prompt('录入本次监测价格；接入平台连接器后将自动同步。', `更新 ${row.competitor_name}`, { inputValue: String(row.current_price || 0), inputPattern: /^\d+(\.\d{1,2})?$/, inputErrorMessage: '请输入有效价格' })
    const res = await api.scan_automation_competitor(row.id, { current_price: Number(value), rank: row.rank, activity: row.activity })
    if (res.data.status !== 200) throw new Error(res.data.msg)
    ElMessage.success('竞品快照已更新')
    await Promise.all([loadCompetitors(), loadOverview()])
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.message || '更新失败') }
}
function makeCreative(productId) { creativeForm.product_id = productId; activeTab.value = 'creative'; generateCreative() }
async function generateCreative() {
  creativeLoading.value = true
  creativePublish.value = false
  try {
    const res = await api.generate_creative_kit({ ...creativeForm })
    if (res.data.status !== 200) throw new Error(res.data.msg)
    creativeKit.value = res.data.data
    inspectResult.value = null
  } catch (error) { ElMessage.error(error?.message || '生成失败') } finally { creativeLoading.value = false }
}
function stopCreativeAutoTimer() {
  if (creativeAutoTimer) clearInterval(creativeAutoTimer)
  creativeAutoTimer = null
}
function startCreativeAutoTimer() {
  stopCreativeAutoTimer()
  creativeAutoTimer = window.setInterval(pollCreativeAuto, 2000)
}
async function restoreCreativeAutoRun() {
  const res = await api.creative_auto_current()
  if (res.data.status !== 200) throw new Error(res.data.msg || '自动上架状态恢复失败')
  creativeAutoRun.value = res.data.data || null
  const output = creativeAutoRun.value?.output || {}
  if (output.scope) creativeAutoScope.value = output.scope
  if (output.channel) creativeForm.channel = output.channel
  if (['running', 'stopping'].includes(creativeAutoRun.value?.status)) {
    startCreativeAutoTimer()
  } else {
    stopCreativeAutoTimer()
  }
}
async function pollCreativeAuto() {
  if (!creativeAutoRun.value?.id) return
  try {
    const res = await api.creative_auto_status(creativeAutoRun.value.id)
    if (res.data.status !== 200) throw new Error(res.data.msg || '自动上架状态获取失败')
    creativeAutoRun.value = res.data.data
    if (!['running', 'stopping'].includes(creativeAutoRun.value.status)) {
      stopCreativeAutoTimer()
      await Promise.all([loadProducts(), loadOverview()])
      ElMessage.success(creativeAutoRun.value.summary || '自动上架任务结束')
    }
  } catch (error) {
    stopCreativeAutoTimer()
    ElMessage.error(error?.message || '自动上架状态获取失败')
  }
}
async function startCreativeAuto() {
  creativeAutoStarting.value = true
  try {
    const res = await api.start_creative_auto({ scope: creativeAutoScope.value, channel: creativeForm.channel, publish: true })
    if (res.data.status === 409 && res.data.data?.id) {
      creativeAutoRun.value = res.data.data
      startCreativeAutoTimer()
      ElMessage.info('自动上架任务已经在运行，已恢复当前进度')
      return
    }
    if (![200, 202].includes(res.data.status)) throw new Error(res.data.msg || '自动上架启动失败')
    creativeAutoRun.value = res.data.data
    startCreativeAutoTimer()
    await pollCreativeAuto()
  } catch (error) {
    ElMessage.error(error?.response?.data?.msg || error?.message || '自动上架启动失败')
  } finally { creativeAutoStarting.value = false }
}
async function stopCreativeAuto() {
  if (!creativeAutoRun.value?.id) return
  creativeAutoStopping.value = true
  try {
    const res = await api.stop_creative_auto(creativeAutoRun.value.id)
    if (res.data.status !== 200) throw new Error(res.data.msg || '结束请求失败')
    creativeAutoRun.value = res.data.data
  } catch (error) { ElMessage.error(error?.message || '结束请求失败') } finally { creativeAutoStopping.value = false }
}
async function applyCreativeImage() {
  const image = creativeKit.value?.image
  if (!creativeForm.product_id || !image?.url && !image?.b64_json) {
    ElMessage.warning('请先生成一张可用主图')
    return
  }
  creativeApplying.value = true
  try {
    const res = await api.apply_creative_image({
      product_id: creativeForm.product_id,
      image,
      publish: creativePublish.value,
    })
    if (res.data.status !== 200) throw new Error(res.data.msg || '主图保存失败')
    creativeKit.value = { ...creativeKit.value, applied_image: res.data.data }
    ElMessage.success(res.data.msg || '主图已保存')
    await loadProducts()
  } catch (error) { ElMessage.error(error?.message || '主图保存失败') } finally { creativeApplying.value = false }
}
function videoStatusLabel(status) {
  return ({ queued: '排队中', in_progress: '生成中', completed: '已完成', failed: '生成失败' })[status] || status || '处理中'
}
async function generateVideo() {
  videoLoading.value = true
  if (videoTimer) { clearInterval(videoTimer); videoTimer = null }
  try {
    const res = await api.agnes_video_create({ prompt: videoPrompt.value.trim(), mode: 'text', seconds: '5', aspect_ratio: videoAspect.value })
    const body = res.data || {}
    if (![200, 202].includes(body.status)) throw new Error(body.msg || '视频任务创建失败')
    videoTask.value = body.data || {}
    if (videoTask.value.video_id) {
      videoTimer = setInterval(pollVideo, 3000)
      await pollVideo()
    }
  } catch (error) { ElMessage.error(error?.message || '视频任务创建失败') } finally { videoLoading.value = false }
}
async function pollVideo() {
  if (!videoTask.value?.video_id) return
  try {
    const res = await api.agnes_video_status(videoTask.value.video_id)
    const body = res.data || {}
    if (body.status !== 200) throw new Error(body.msg || '视频状态查询失败')
    videoTask.value = { ...videoTask.value, ...(body.data || {}) }
    if (['completed', 'failed'].includes(videoTask.value.status) && videoTimer) {
      clearInterval(videoTimer); videoTimer = null
    }
  } catch (error) {
    if (videoTimer) { clearInterval(videoTimer); videoTimer = null }
    ElMessage.error(error?.message || '视频状态查询失败')
  }
}
async function inspectCreative() {
  inspectLoading.value = true
  try {
    const res = await api.inspect_creative({ ...inspectForm })
    if (res.data.status !== 200) throw new Error(res.data.msg)
    inspectResult.value = res.data.data
    creativeKit.value = null
  } catch (error) { ElMessage.error(error?.message || '质检失败') } finally { inspectLoading.value = false }
}

onMounted(loadCreativeWorkspace)
onUnmounted(stopCreativeAutoTimer)
onUnmounted(() => { if (videoTimer) clearInterval(videoTimer) })
</script>

<style scoped>
.automation-page { color:#171714; min-width:0; }
.page-head { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; margin-bottom:14px; }
.title-line { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
h1 { margin:0; font-size:24px; line-height:1.25; font-weight:700; letter-spacing:0; }
.page-head p,.section-head p { margin:5px 0 0; color:#6f6b63; font-size:13px; }
.live-badge { display:inline-flex; align-items:center; gap:6px; border:1px solid #c9ddd8; color:#16665d; background:#f2faf8; border-radius:999px; padding:4px 8px; font-size:12px; }
.live-badge i,.source-item i { width:7px; height:7px; border-radius:50%; background:#16836f; }
.head-actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }
.source-bar { min-height:34px; display:flex; align-items:center; gap:16px; padding:7px 10px; background:#eeede9; border:1px solid #e1dfd8; border-radius:6px; font-size:12px; color:#5e5a52; overflow-x:auto; white-space:nowrap; }
.source-item { display:inline-flex; align-items:center; gap:5px; }
.source-item i.warn { background:#c87916; }.generated { margin-left:auto; }
.generated-media { display:flex; flex-direction:column; gap:6px; margin:14px 0; padding:10px; border:1px solid #dcebe7; background:#f5fbf9; border-radius:8px; }
.generated-image { width:100%; max-height:280px; border-radius:6px; background:#eef5f2; }
.creative-apply-bar { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-top:8px; }
.apply-hint { color:#66756f; line-height:1.5; }
.auto-listing-panel { display:flex; align-items:center; justify-content:space-between; gap:18px; margin-bottom:18px; padding:16px 18px; background:#f4faf7; border:1px solid #cfe6dc; border-radius:8px; }
.auto-listing-copy { min-width:0; flex:1; }.auto-listing-title { display:flex; align-items:center; gap:7px; }.auto-listing-title h3 { margin:0; font-size:16px; }.auto-listing-copy p { margin:7px 0 0; color:#5f6f68; font-size:12px; line-height:1.55; }.auto-listing-controls { display:flex; align-items:center; gap:8px; flex-shrink:0; }.auto-progress { display:flex; align-items:center; gap:10px; margin-top:10px; max-width:560px; }.auto-progress .el-progress { flex:1; min-width:180px; }.auto-progress span { color:#5f6f68; font-size:12px; white-space:nowrap; }.auto-result-list { display:flex; flex-wrap:wrap; gap:6px 12px; margin-top:8px; font-size:12px; }.auto-result-list .ok { color:#19704f; }.auto-result-list .bad { color:#a04438; }
.advanced-tools { margin-top:18px; border-top:1px solid #dedbd4; }
.advanced-tools summary { cursor:pointer; padding:14px 2px; color:#5f5b54; font-size:13px; font-weight:600; }
.advanced-tools summary:focus-visible { outline:2px solid #0f766e; outline-offset:3px; }
.advanced-scope { display:flex; align-items:center; gap:12px; margin:0 0 14px; color:#5f5b54; font-size:13px; }
.video-panel { margin-top:18px; padding-top:18px; border-top:1px solid #e5e2da; }
.video-actions { display:flex; gap:10px; align-items:center; margin-top:10px; }
.video-result { display:flex; flex-direction:column; gap:8px; margin-top:12px; }
.generated-video { width:100%; max-height:360px; border-radius:8px; background:#111; }
.workspace-nav { display:flex; gap:4px; border-bottom:1px solid #dad8d1; margin-top:18px; overflow-x:auto; }
.workspace-nav button { height:42px; display:flex; align-items:center; gap:7px; border:0; border-bottom:2px solid transparent; padding:0 14px; background:transparent; color:#68645d; font:inherit; font-size:13px; cursor:pointer; white-space:nowrap; }
.workspace-nav button:hover { color:#0f766e; background:#f4f8f7; }.workspace-nav button.active { color:#0b625b; border-bottom-color:#0f766e; font-weight:650; }
.workspace { padding-top:18px; }
.metric-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border:1px solid #dcd9d1; border-radius:8px; background:#fff; }
.metric-cell { min-height:110px; padding:18px 20px; border-right:1px solid #e5e2dc; }.metric-cell:last-child { border-right:0; }
.metric-cell span,.metric-cell small { display:block; color:#777269; font-size:12px; }.metric-cell strong { display:block; margin:7px 0 6px; font-size:25px; line-height:1.15; letter-spacing:0; }
.positive { color:#087160 !important; }.negative { color:#b23b32 !important; }.quiet { color:#777269; }
.overview-grid { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(300px,.8fr); gap:18px; margin-top:18px; }
.insight-panel,.run-panel,.data-section,.modules-section,.report-sheet,.creative-form,.creative-output { background:#fff; border:1px solid #dedbd4; border-radius:8px; }
.insight-panel,.run-panel,.modules-section,.data-section,.creative-form,.creative-output { padding:18px; }
.section-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:14px; }.section-head h2 { margin:0; font-size:16px; line-height:1.35; letter-spacing:0; }.section-head p { max-width:72ch; }
.insight-list,.run-list { display:grid; }.insight-row { display:grid; grid-template-columns:34px 1fr auto; align-items:center; gap:10px; padding:12px 0; border-top:1px solid #eceae5; }.insight-row:first-child { border-top:0; }
.insight-row strong,.run-row strong { font-size:13px; }.insight-row p,.run-row p { margin:3px 0 0; color:#777269; font-size:12px; line-height:1.45; }
.severity { width:30px; height:30px; display:grid; place-items:center; border-radius:50%; background:#f3f2ef; color:#777269; }.severity.warning { background:#fff4df; color:#a65f0b; }.severity.danger { background:#fcede9; color:#b23b32; }.severity.success { background:#eaf7f3; color:#087160; }
.run-row { display:grid; grid-template-columns:10px 1fr auto; gap:9px; align-items:start; padding:11px 0; border-top:1px solid #eceae5; }.run-row:first-child { border-top:0; }.run-row time { color:#8a857d; font-size:11px; white-space:nowrap; }.run-dot { width:7px; height:7px; border-radius:50%; margin-top:5px; background:#9a958d; }.run-dot.success { background:#16836f; }.run-dot.failed { background:#b23b32; }
.modules-section,.data-section { margin-top:18px; }.module-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
.module-item { min-width:0; min-height:72px; display:grid; grid-template-columns:38px 1fr 18px; gap:10px; align-items:center; padding:11px; border:1px solid #e3e1db; border-radius:7px; background:#fbfbfa; text-align:left; cursor:pointer; color:inherit; }.module-item:hover { border-color:#8abcb4; background:#f4faf8; }.module-item:focus-visible,.workspace-nav button:focus-visible { outline:3px solid rgba(15,118,110,.25); outline-offset:2px; }
.module-icon { width:36px; height:36px; border-radius:7px; display:grid; place-items:center; background:#eeede9; color:#625f58; }.module-icon.ready { background:#e8f5f1; color:#0f766e; }.module-icon.attention { background:#fff1da; color:#a65f0b; }.module-icon.compact { width:32px; height:32px; }
.module-copy { min-width:0; }.module-copy strong,.module-copy small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.module-copy strong { font-size:13px; }.module-copy small { margin-top:4px; color:#777269; font-size:11px; }.arrow { color:#aaa59c; }
.finance-heading { margin-bottom:18px; }.report-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }.report-sheet { padding:0 16px 10px; overflow:hidden; }.report-title { margin:0 -16px 8px; padding:14px 16px; background:#f3f2ef; border-bottom:1px solid #dedbd4; }.report-title span,.report-title small { display:block; }.report-title span { font-weight:700; }.report-title small { color:#777269; margin-top:3px; }
.report-row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 0; border-bottom:1px solid #eceae5; font-size:13px; }.report-row:last-child { border-bottom:0; }.report-row.result { margin-top:3px; font-weight:700; color:#0b625b; }.report-row.cost strong { color:#a33d35; }
.finance-notice { display:flex; gap:8px; align-items:flex-start; margin-top:12px; padding:10px 12px; border-radius:6px; background:#fff7e8; color:#7a521b; font-size:12px; line-height:1.5; }
.workflow-summary { display:flex; align-items:center; gap:24px; padding:14px 16px; margin-bottom:12px; border:1px solid #dedbd4; border-radius:8px; background:#fff; color:#6f6b63; font-size:13px; }.workflow-summary strong { margin-right:4px; color:#171714; font-size:20px; }.workflow-summary .guard { margin-left:auto; display:inline-flex; align-items:center; gap:5px; color:#0b625b; }
.workflow-table { border:1px solid #dedbd4; border-radius:8px; overflow:hidden; }.rule-name { display:flex; gap:10px; align-items:center; }.rule-name strong,.rule-name small { display:block; }.rule-name small { color:#777269; margin-top:3px; font-size:11px; }
.toolbar-line { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; color:#6f6b63; font-size:13px; }.flag { margin:2px 4px 2px 0; }.aftersale-summary { display:flex; flex-wrap:wrap; gap:0; margin-bottom:14px; border:1px solid #dedbd4; border-radius:8px; background:#fff; }.aftersale-summary div { min-width:140px; padding:14px 18px; border-right:1px solid #e6e3dd; }.aftersale-summary strong,.aftersale-summary span { display:block; }.aftersale-summary strong { font-size:22px; }.aftersale-summary span { color:#777269; font-size:12px; margin-top:3px; }
.creative-grid { display:grid; grid-template-columns:minmax(300px,.7fr) minmax(0,1.3fr); gap:18px; }.creative-form h3,.creative-output h3 { margin:0 0 14px; font-size:15px; }.form-divider { height:1px; background:#e5e2dc; margin:22px 0; }.dimension-row,.dialog-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }.creative-output { min-height:480px; }.creative-output :deep(.el-empty) { height:100%; }.output-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; border-bottom:1px solid #e5e2dc; padding-bottom:14px; }.output-head span { color:#777269; font-size:11px; }.output-head h3 { margin:3px 0 0; font-size:18px; }.brief-block { padding:14px 0; }.brief-block strong { font-size:12px; }.brief-block p { color:#5f5b54; line-height:1.6; font-size:13px; }.size-plan { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); border:1px solid #dedbd4; border-radius:7px; }.size-plan div { padding:12px; border-right:1px solid #dedbd4; }.size-plan div:last-child { border-right:0; }.size-plan span,.size-plan strong { display:block; }.size-plan span { color:#777269; font-size:11px; }.size-plan strong { margin-top:4px; font-size:13px; }.detail-plan { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:16px 0; }.detail-plan strong { font-size:12px; }.detail-plan ul { margin:7px 0 0; padding-left:16px; color:#5f5b54; font-size:12px; line-height:1.65; }.connector-note { margin:14px 0 0; color:#777269; font-size:11px; }.issue-line { margin:6px 0; color:#8a5210; font-size:13px; }
@media (max-width:1100px) { .metric-strip,.module-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }.metric-cell:nth-child(2) { border-right:0; }.metric-cell:nth-child(-n+2) { border-bottom:1px solid #e5e2dc; }.overview-grid { grid-template-columns:1fr; }.report-grid { grid-template-columns:1fr; }.creative-grid { grid-template-columns:1fr; } }
@media (max-width:680px) { .auto-listing-panel { align-items:stretch; flex-direction:column; }.auto-listing-controls { justify-content:flex-start; }.auto-progress { align-items:stretch; flex-direction:column; }.auto-progress span { white-space:normal; } }
@media (max-width:760px) { .page-head { flex-direction:column; }.head-actions { width:100%; justify-content:flex-start; }.generated { margin-left:0; }.metric-strip,.module-grid { grid-template-columns:1fr; }.metric-cell { border-right:0; border-bottom:1px solid #e5e2dc; }.metric-cell:last-child { border-bottom:0; }.insight-row { grid-template-columns:30px 1fr; }.insight-row .el-button { grid-column:2; justify-self:start; }.workflow-summary { align-items:flex-start; flex-wrap:wrap; }.workflow-summary .guard { width:100%; margin-left:0; }.size-plan,.detail-plan,.dimension-row,.dialog-grid { grid-template-columns:1fr; }.size-plan div { border-right:0; border-bottom:1px solid #dedbd4; }.size-plan div:last-child { border-bottom:0; } }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior:auto !important; } }
</style>
