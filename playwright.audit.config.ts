import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e',testMatch:'app-audit.spec.ts',timeout:25000,workers:3,retries:0,
  reporter:[['list'],['json',{outputFile:'output/playwright/audit-results.json'}]],
  outputDir:'./output/playwright/audit',
  use:{baseURL:process.env.E2E_BASE_URL || 'http://127.0.0.1:8090',screenshot:'only-on-failure',trace:'retain-on-failure'},
  projects:[
    {name:'desktop',use:{browserName:'chromium',channel:'chrome',viewport:{width:1440,height:1000}}},
    {name:'tablet',use:{browserName:'chromium',viewport:{width:834,height:1112}}},
    {name:'phone',use:{browserName:'chromium',viewport:{width:390,height:844}}},
    {name:'firefox',use:{browserName:'firefox',viewport:{width:1440,height:1000}},grep:/critical|login/},
    {name:'webkit',use:{browserName:'webkit',viewport:{width:390,height:844}},grep:/critical|login/},
  ],
});
