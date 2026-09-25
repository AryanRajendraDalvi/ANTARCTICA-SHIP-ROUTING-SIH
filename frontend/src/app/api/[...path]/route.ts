import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.NCPOR_API_URL || 'http://localhost:8001';

function errorDetail(error: unknown) {
  return error instanceof Error ? error.message : 'Unknown proxy error';
}

// Next.js 15: params is a Promise and must be awaited
export async function GET(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path: pathArr } = await context.params;
  const path = pathArr.join('/');
  const search = req.nextUrl.search;
  const url = `${BACKEND}/api/${path}${search}`;

  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) return NextResponse.json({ error: `Backend ${res.status}` }, { status: res.status });

    const contentType = res.headers.get('content-type') || '';

    // Pass binary responses (PNG images, etc.) through directly - don't try to parse as JSON
    if (contentType.includes('image/') || contentType.includes('application/octet-stream')) {
      const buffer = await res.arrayBuffer();
      return new NextResponse(buffer, {
        status: res.status,
        headers: {
          'Content-Type': contentType,
          'Cache-Control': 'no-cache',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    return NextResponse.json({ error: 'Backend unavailable', detail: errorDetail(error) }, { status: 503 });
  }
}

export async function POST(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path: pathArr } = await context.params;
  const path = pathArr.join('/');
  const body = await req.json();
  const url = `${BACKEND}/api/${path}`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await res.json();
    // Preserve backend failures. Returning a 200 here made a failed route
    // calculation look like an empty, successful route response in the UI.
    return NextResponse.json(data, { status: res.status });
  } catch (error: unknown) {
    return NextResponse.json({ error: 'Backend unavailable', detail: errorDetail(error) }, { status: 503 });
  }
}
