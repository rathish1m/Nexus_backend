/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './app_settings/templates/**/*.html',
    './backoffice/templates/**/*.html',
    './client_app/templates/**/*.html',
    './customers/templates/**/*.html',
    './dashboard_bi/templates/**/*.html',
    './geo_regions/templates/**/*.html',
    './kyc_management/templates/**/*.html',
    './main/templates/**/*.html',
    './orders/templates/**/*.html',
    './sales/templates/**/*.html',
    './stock/templates/**/*.html',
    './subscriptions/templates/**/*.html',
    './tech/templates/**/*.html',
    './user/templates/**/*.html',
    './website/**/*.html',
    './static/js/**/*.js',
    './static/src/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
