#ifndef BRIDGE_H
#define BRIDGE_H

#include "types.h"

/*
 * AI bridge: a framed protocol over COM2 (0x2F8) to a host-side adapter that
 * forwards prompts to a local model. Frame layout (little-endian):
 *
 *   MAGIC(4 = "AIOS") | type(1) | seq(2) | len(4) | payload(len) | crc32(4)
 *   type: 0=req 1=resp 2=err
 *   crc32 = standard IEEE CRC-32 of the payload bytes (matches Python zlib.crc32)
 *
 * v1 is request/response (no streaming). See DESIGN.md §9 and host/ai-bridge/.
 */
void bridge_init(void);

/* Send `prompt` as a request and block (with timeout) for a response. Writes a
 * NUL-terminated reply into `out`. Returns:
 *   >=0  reply length (success)
 *   -1   timeout / framing error (no bridge, or corrupt stream)
 *   -2   bridge replied with an error frame; `out` holds the error message
 *        (e.g. the backend/model failed) */
int bridge_request(const char *prompt, u32 prompt_len, char *out, u32 out_max);

#endif
