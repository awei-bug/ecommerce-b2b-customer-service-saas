import * as echarts from 'echarts'

const chartMap = new WeakMap()

export default {
  install(app) {
    app.config.globalProperties.$echarts = (elementOrId, option) => {
      try {
        let el = elementOrId
        if (typeof elementOrId === 'string') {
          el = document.getElementById(elementOrId)
        }
        if (!el) {
          console.warn('[echarts] container missing', elementOrId)
          return null
        }
        let chart = echarts.getInstanceByDom(el)
        if (!chart) {
          chart = echarts.init(el)
        }
        chart.setOption(option, true)
        chartMap.set(el, chart)
        // 自适应
        const onResize = () => {
          try { chart.resize() } catch (e) {}
        }
        window.addEventListener('resize', onResize)
        return chart
      } catch (err) {
        console.error('[echarts] render failed', err)
        return null
      }
    }
  },
}
