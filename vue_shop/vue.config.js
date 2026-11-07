const { defineConfig } = require('@vue/cli-service')
const AutoImport = require('unplugin-auto-import/webpack')
const Components = require('unplugin-vue-components/webpack')
const { ElementPlusResolver } = require('unplugin-vue-components/resolvers')
const apiProxyTarget = process.env.VUE_APP_API_PROXY_TARGET || 'http://127.0.0.1:5000'

module.exports = defineConfig({
  transpileDependencies: true,
  // 样板店 / Nginx：后台挂在 /admin/
  publicPath: process.env.VUE_APP_PUBLIC_PATH || '/admin/',
  devServer: {
    port: 8080,
    host: '0.0.0.0',
    proxy: {
      '/static': { target: apiProxyTarget, changeOrigin: true },
      '^/(user|products|product|orders|order|pay|menu|roles|role|permissions|categorys|attributes|attribute|freight|expresses|dashboard|upload_img|health|api)': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  configureWebpack: {
    plugins: [
      AutoImport({
        resolvers: [ElementPlusResolver()]
      }),
      Components({
        resolvers: [ElementPlusResolver()]
      })
    ]
  }
})
