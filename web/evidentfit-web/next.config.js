/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable static export for Azure Static Web Apps
  output: 'export',
  trailingSlash: true,
  distDir: 'out',
  
  // Environment variables for Azure
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || 'https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io',
    NEXT_PUBLIC_DEMO_USER: process.env.NEXT_PUBLIC_DEMO_USER || 'demo',
    NEXT_PUBLIC_DEMO_PW: process.env.NEXT_PUBLIC_DEMO_PW || 'demo123',
  },
  
  // Optimize for production
  compress: true,
  poweredByHeader: false,
  
  // Image optimization
  images: {
    unoptimized: true, // Required for static export
  },
}

module.exports = nextConfig
