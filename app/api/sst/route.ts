import { NextResponse } from 'next/server';

export async function GET() {
  const apiKey = process.env.DEEPGRAM_API_KEY;
  const projectId = process.env.DEEPGRAM_PROJECT_ID;

  if (!apiKey) {
    console.error('DEEPGRAM_API_KEY is not set');
    return NextResponse.json({ error: 'DEEPGRAM_API_KEY is not set' }, { status: 500 });
  }

  if (!projectId) {
    console.error('DEEPGRAM_PROJECT_ID is not set');
    return NextResponse.json({ error: 'DEEPGRAM_PROJECT_ID is not set' }, { status: 500 });
  }

  try {
    return NextResponse.json({ key: apiKey });
  } catch (error) {
    console.error('Error generating Deepgram key:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}