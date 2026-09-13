import asyncio
import base64
import json
import subprocess
from typing import Any, Dict, List, NoReturn, Tuple

from app.clients.http_client import HttpClientFactory
from app.logging import logger
from settings import config


class GeminiSpeechService:
    @classmethod
    def _raise_provider_error(cls: type['GeminiSpeechService'], error: Exception) -> NoReturn:
        status_code = getattr(error, 'status_code', None) or getattr(error, 'code', None)
        error_text = str(error).casefold()
        logger.error('gemini_speech_provider_error status=%s error=%s', status_code, error)
        if (
            status_code in {400, 401, 403}
            or '400 bad request' in error_text
            or '401 unauthorized' in error_text
            or '403 forbidden' in error_text
            or 'api key' in error_text
            or 'unauthorized' in error_text
        ):
            raise ValueError(
                'Artemox отклонил Gemini TTS-запрос. Проверьте GEMINI_API_KEY, '
                'GEMINI_NATIVE_BASE_URL, GEMINI_TTS_MODEL и GEMINI_TTS_VOICE.'
            ) from error
        raise error

    @classmethod
    async def synthesize(cls: type['GeminiSpeechService'], text: str) -> bytes:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError('Нельзя синтезировать пустой текст')
        logger.info(
            'gemini_speech_started chars=%s model=%s voice=%s',
            len(clean_text),
            config.gemini.tts_model,
            config.gemini.tts_voice,
        )
        try:
            pcm_audio = await asyncio.to_thread(cls._request_pcm, clean_text)
            logger.info('gemini_speech_pcm_received bytes=%s', len(pcm_audio))
            audio = await asyncio.to_thread(cls._convert_to_telegram_ogg, pcm_audio)
            logger.info('gemini_speech_ogg_converted bytes=%s', len(audio))
        except Exception as error:
            cls._raise_provider_error(error)
        if not audio:
            raise ValueError('Artemox не вернул аудио для TTS')
        logger.info('gemini_speech_completed bytes=%s', len(audio))
        return audio

    @classmethod
    def _request_pcm(cls: type['GeminiSpeechService'], text: str) -> bytes:
        if not config.gemini.api_key:
            raise ValueError('Не задан GEMINI_API_KEY для синтеза речи.')
        url = (
            f'{cls._native_base_url()}/v1beta/models/'
            f'{config.gemini.tts_model}:streamGenerateContent?alt=sse'
        )
        payload: Dict[str, Any] = {
            'model': config.gemini.tts_model,
            'contents': [{'role': 'user', 'parts': [{'text': text}]}],
            'generationConfig': {
                'responseModalities': ['AUDIO'],
                'speechConfig': {
                    'voiceConfig': {
                        'prebuiltVoiceConfig': {
                            'voiceName': config.gemini.tts_voice,
                        }
                    }
                },
            },
        }
        logger.info('gemini_speech_http_started url=%s', url)
        audio_chunks = bytearray()
        with HttpClientFactory.get_httpx_proxy_client('gemini', timeout=120.0) as client:
            with client.stream(
                'POST',
                url,
                headers={
                    'x-goog-api-key': config.gemini.api_key,
                    'Content-Type': 'application/json',
                },
                json=payload,
            ) as response:
                logger.info(
                    'gemini_speech_http_started status=%s content_type=%s',
                    response.status_code,
                    response.headers.get('content-type', ''),
                )
                if response.is_error:
                    error_body = response.read().decode('utf-8', errors='replace')[:2000]
                    raise ValueError(
                        f'Artemox TTS HTTP {response.status_code}: {error_body}'
                    )
                event_lines: List[str] = []
                pending_payload = ''
                for raw_line in response.iter_lines():
                    line = raw_line.decode('utf-8') if isinstance(raw_line, bytes) else raw_line
                    line = line.strip()
                    if not line.strip():
                        payload = ''.join(event_lines).strip()
                        pending_payload += payload
                        chunk, finished, complete = cls._parse_sse_event([pending_payload])
                        audio_chunks.extend(chunk)
                        event_lines = []
                        if complete:
                            pending_payload = ''
                        if finished and complete:
                            break
                        continue
                    if line.startswith('data:'):
                        event_lines.append(line[5:].lstrip())
                    elif line.startswith(('event:', 'id:', 'retry:')):
                        continue
                    else:
                        event_lines.append(line)
                if event_lines:
                    pending_payload += ''.join(event_lines).strip()
                    chunk, _, complete = cls._parse_sse_event([pending_payload])
                    audio_chunks.extend(chunk)
                    if not complete:
                        logger.warning(
                            'gemini_speech_sse_incomplete_event chars=%s preview=%s',
                            len(pending_payload),
                            pending_payload[:200],
                        )
        logger.info('gemini_speech_http_completed bytes=%s', len(audio_chunks))
        if not audio_chunks:
            raise ValueError('Gemini не вернул аудио в streamGenerateContent')
        return bytes(audio_chunks)

    @classmethod
    def _parse_sse_event(
        cls: type['GeminiSpeechService'],
        event_lines: List[str],
    ) -> Tuple[bytes, bool, bool]:
        payload = ''.join(event_lines).strip()
        if not payload:
            return b'', False, True
        if payload == '[DONE]':
            return b'', True, True
        try:
            response_data: Dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            return b'', False, False
        audio = bytearray()
        finished = False
        for candidate in response_data.get('candidates', []):
            finished = finished or bool(candidate.get('finishReason'))
            content = candidate.get('content') or {}
            for part in content.get('parts', []):
                inline_data = part.get('inlineData') or part.get('inline_data') or {}
                encoded_audio = inline_data.get('data')
                if encoded_audio:
                    audio.extend(base64.b64decode(encoded_audio))
        return bytes(audio), finished, True

    @classmethod
    def _native_base_url(cls: type['GeminiSpeechService']) -> str:
        native_base_url = config.gemini.native_base_url
        if native_base_url:
            return native_base_url.rstrip('/')
        return config.gemini.base_url.removesuffix('/v1')

    @classmethod
    def _convert_to_telegram_ogg(
        cls: type['GeminiSpeechService'],
        pcm_audio: bytes,
    ) -> bytes:
        if not pcm_audio:
            raise ValueError('Gemini вернул пустое аудио')
        result = subprocess.run(
            [
                'ffmpeg',
                '-hide_banner',
                '-loglevel',
                'error',
                '-f',
                's16le',
                '-ar',
                '24000',
                '-ac',
                '1',
                '-i',
                'pipe:0',
                '-c:a',
                'libopus',
                '-f',
                'ogg',
                'pipe:1',
            ],
            input=pcm_audio,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            error = result.stderr.decode('utf-8', errors='replace').strip()
            raise RuntimeError(f'Не удалось конвертировать TTS в OGG/Opus: {error}')
        return result.stdout
