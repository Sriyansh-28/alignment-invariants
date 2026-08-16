/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The Gemini key is read only inside route handlers (server-side). It is
  // never added to `env` here, because anything placed in `env` or prefixed
  // NEXT_PUBLIC_ is inlined into the client bundle.
};

export default nextConfig;
