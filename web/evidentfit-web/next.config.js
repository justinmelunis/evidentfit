/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable static export for Azure Static Web Apps
  output: 'export',
  trailingSlash: true,
  distDir: 'out',
  
  // Environment variables for Azure
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000',
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
