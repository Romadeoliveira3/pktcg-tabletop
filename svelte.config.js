import adapter from '@sveltejs/adapter-static'
import 'dotenv/config'

/** @type {import('@sveltejs/kit').Config} */
const config = {
   kit: {
      adapter: adapter({
         pages: process.env.BUILD_DIR || 'build'
      }),
      paths: {
         base: process.env.VITE_ENV === 'prod' ? '/simulator/pktcg-simulator' : ''
      }
   }
}

export default config
