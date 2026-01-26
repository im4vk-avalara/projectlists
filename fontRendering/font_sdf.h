/*
 * font_sdf.h - SDF Font Rendering using stb_truetype
 * 
 * Single-header library for rendering scalable text using Signed Distance Fields.
 * Uses stb_truetype for TTF parsing and SDF generation.
 * 
 * Copyright (c) 2026 Avinash Kumar
 * All rights reserved.
 * 
 * USAGE:
 *   #define FONT_SDF_IMPLEMENTATION
 *   #include "font_sdf.h"
 * 
 *   SdfFont font = SdfFontLoad("font.ttf");
 *   SdfFontDrawText(&font, "Hello", 100, 100, 48.0f, WHITE);
 *   SdfFontUnload(&font);
 */

#ifndef FONT_SDF_H
#define FONT_SDF_H

#include "raylib.h"

#ifdef __cplusplus
extern "C" {
#endif

// Configuration
#define SDF_FONT_SIZE       64      // Size to render glyphs at for SDF
#define SDF_PADDING         8       // Padding around each glyph
#define SDF_ON_EDGE_VALUE   128     // Value at the glyph edge (0-255)
#define SDF_PIXEL_DIST_SCALE 32.0f  // How many pixels the SDF covers
#define SDF_MAX_GLYPHS      128     // Maximum glyphs to cache
#define SDF_ATLAS_SIZE      1024    // Atlas texture size

typedef struct {
    int codepoint;
    float advanceWidth;     // Horizontal advance in pixels at SDF_FONT_SIZE
    float leftBearing;      // Left side bearing in pixels
    int x0, y0, x1, y1;     // Bounding box in atlas
    int width, height;      // Glyph bitmap dimensions
    int xoff, yoff;         // Offset from origin
} SdfGlyphInfo;

typedef struct {
    SdfGlyphInfo glyphs[SDF_MAX_GLYPHS];
    int glyphCount;
    Texture2D atlas;
    Shader shader;
    float scale;            // Scale factor used when generating SDFs
    float ascent;           // Font ascent at SDF_FONT_SIZE
    float descent;          // Font descent at SDF_FONT_SIZE
    float lineGap;          // Line gap at SDF_FONT_SIZE
} SdfFont;

// Public API
SdfFont SdfFontLoad(const char *ttfPath);
void SdfFontDrawText(SdfFont *font, const char *text, float x, float y, float fontSize, Color color);
float SdfFontMeasureText(SdfFont *font, const char *text, float fontSize);
void SdfFontUnload(SdfFont *font);

#ifdef __cplusplus
}
#endif

#endif // FONT_SDF_H

// =============================================================================
// IMPLEMENTATION
// =============================================================================

#ifdef FONT_SDF_IMPLEMENTATION

#define STB_TRUETYPE_IMPLEMENTATION
#include "stb_truetype.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

// Vertex shader - standard passthrough
static const char *sdfVertexShader = 
    "#version 330\n"
    "in vec3 vertexPosition;\n"
    "in vec2 vertexTexCoord;\n"
    "in vec4 vertexColor;\n"
    "out vec2 fragTexCoord;\n"
    "out vec4 fragColor;\n"
    "uniform mat4 mvp;\n"
    "void main() {\n"
    "    fragTexCoord = vertexTexCoord;\n"
    "    fragColor = vertexColor;\n"
    "    gl_Position = mvp * vec4(vertexPosition, 1.0);\n"
    "}\n";

// Fragment shader - SDF rendering with smoothstep
static const char *sdfFragmentShader = 
    "#version 330\n"
    "in vec2 fragTexCoord;\n"
    "in vec4 fragColor;\n"
    "out vec4 finalColor;\n"
    "uniform sampler2D texture0;\n"
    "void main() {\n"
    "    float dist = texture(texture0, fragTexCoord).r;\n"
    "    float edge = 0.5;\n"
    "    float smoothing = 0.1;\n"
    "    float alpha = smoothstep(edge - smoothing, edge + smoothing, dist);\n"
    "    finalColor = vec4(fragColor.rgb, fragColor.a * alpha);\n"
    "}\n";

// Find glyph by codepoint
static SdfGlyphInfo* find_glyph(SdfFont *font, int codepoint) {
    for (int i = 0; i < font->glyphCount; i++) {
        if (font->glyphs[i].codepoint == codepoint) {
            return &font->glyphs[i];
        }
    }
    return NULL;
}

SdfFont SdfFontLoad(const char *ttfPath) {
    SdfFont font = {0};
    
    // Load TTF file
    int dataSize = 0;
    unsigned char *ttfData = LoadFileData(ttfPath, &dataSize);
    if (!ttfData || dataSize == 0) {
        TraceLog(LOG_ERROR, "Failed to load TTF file: %s", ttfPath);
        return font;
    }
    TraceLog(LOG_INFO, "Loaded TTF file: %s (%d bytes)", ttfPath, dataSize);
    
    // Initialize stb_truetype
    stbtt_fontinfo info;
    if (!stbtt_InitFont(&info, ttfData, stbtt_GetFontOffsetForIndex(ttfData, 0))) {
        TraceLog(LOG_ERROR, "Failed to initialize font: %s", ttfPath);
        UnloadFileData(ttfData);
        return font;
    }
    
    // Calculate scale for desired font size
    font.scale = stbtt_ScaleForPixelHeight(&info, SDF_FONT_SIZE);
    
    // Get font metrics
    int ascent, descent, lineGap;
    stbtt_GetFontVMetrics(&info, &ascent, &descent, &lineGap);
    font.ascent = ascent * font.scale;
    font.descent = descent * font.scale;
    font.lineGap = lineGap * font.scale;
    
    // Allocate atlas
    int atlasWidth = SDF_ATLAS_SIZE;
    int atlasHeight = SDF_ATLAS_SIZE;
    unsigned char *atlasData = (unsigned char *)calloc(atlasWidth * atlasHeight, 1);
    
    // Pack glyphs - simple row-based packing
    int cursorX = SDF_PADDING;
    int cursorY = SDF_PADDING;
    int rowHeight = 0;
    
    // Generate SDF for ASCII printable characters (32-126)
    for (int c = 32; c <= 126 && font.glyphCount < SDF_MAX_GLYPHS; c++) {
        int glyphIndex = stbtt_FindGlyphIndex(&info, c);
        if (glyphIndex == 0 && c != 32) continue; // Skip missing glyphs (except space)
        
        // Get glyph metrics
        int advanceWidth, leftBearing;
        stbtt_GetGlyphHMetrics(&info, glyphIndex, &advanceWidth, &leftBearing);
        
        // Generate SDF for this glyph
        int width, height, xoff, yoff;
        unsigned char *sdfBitmap = stbtt_GetGlyphSDF(
            &info,
            font.scale,
            glyphIndex,
            SDF_PADDING,
            SDF_ON_EDGE_VALUE,
            SDF_PIXEL_DIST_SCALE,
            &width, &height, &xoff, &yoff
        );
        
        // Handle space character specially
        if (c == 32 || !sdfBitmap) {
            SdfGlyphInfo *glyph = &font.glyphs[font.glyphCount++];
            glyph->codepoint = c;
            glyph->advanceWidth = advanceWidth * font.scale;
            glyph->leftBearing = leftBearing * font.scale;
            glyph->width = 0;
            glyph->height = 0;
            glyph->x0 = 0;
            glyph->y0 = 0;
            glyph->x1 = 0;
            glyph->y1 = 0;
            glyph->xoff = 0;
            glyph->yoff = 0;
            continue;
        }
        
        // Check if we need to move to next row
        if (cursorX + width + SDF_PADDING > atlasWidth) {
            cursorX = SDF_PADDING;
            cursorY += rowHeight + SDF_PADDING;
            rowHeight = 0;
        }
        
        // Check if we've run out of space
        if (cursorY + height + SDF_PADDING > atlasHeight) {
            TraceLog(LOG_WARNING, "Atlas full, stopping at codepoint %d", c);
            stbtt_FreeSDF(sdfBitmap, NULL);
            break;
        }
        
        // Copy SDF bitmap to atlas
        for (int row = 0; row < height; row++) {
            memcpy(
                atlasData + (cursorY + row) * atlasWidth + cursorX,
                sdfBitmap + row * width,
                width
            );
        }
        
        // Store glyph info
        SdfGlyphInfo *glyph = &font.glyphs[font.glyphCount++];
        glyph->codepoint = c;
        glyph->advanceWidth = advanceWidth * font.scale;
        glyph->leftBearing = leftBearing * font.scale;
        glyph->width = width;
        glyph->height = height;
        glyph->x0 = cursorX;
        glyph->y0 = cursorY;
        glyph->x1 = cursorX + width;
        glyph->y1 = cursorY + height;
        glyph->xoff = xoff;
        glyph->yoff = yoff;
        
        // Advance cursor
        cursorX += width + SDF_PADDING;
        if (height > rowHeight) rowHeight = height;
        
        stbtt_FreeSDF(sdfBitmap, NULL);
    }
    
    TraceLog(LOG_INFO, "Generated SDF for %d glyphs", font.glyphCount);
    
    // Create atlas texture
    Image atlasImage = {
        .data = atlasData,
        .width = atlasWidth,
        .height = atlasHeight,
        .format = PIXELFORMAT_UNCOMPRESSED_GRAYSCALE,
        .mipmaps = 1
    };
    font.atlas = LoadTextureFromImage(atlasImage);
    SetTextureFilter(font.atlas, TEXTURE_FILTER_BILINEAR);
    
    // Free atlas data (texture has its own copy)
    free(atlasData);
    UnloadFileData(ttfData);
    
    // Load SDF shader
    font.shader = LoadShaderFromMemory(sdfVertexShader, sdfFragmentShader);
    
    TraceLog(LOG_INFO, "SDF font loaded successfully: %s", ttfPath);
    
    return font;
}

void SdfFontDrawText(SdfFont *font, const char *text, float x, float y, float fontSize, Color color) {
    if (!font || !text || font->glyphCount == 0) return;
    
    // Calculate scale relative to the SDF generation size
    float scale = fontSize / (float)SDF_FONT_SIZE;
    
    float cursorX = x;
    float baseline = y + font->ascent * scale;
    
    BeginShaderMode(font->shader);
    
    for (const char *p = text; *p; p++) {
        int c = (unsigned char)*p;
        
        // Handle newline
        if (c == '\n') {
            cursorX = x;
            baseline += (font->ascent - font->descent + font->lineGap) * scale;
            continue;
        }
        
        SdfGlyphInfo *glyph = find_glyph(font, c);
        if (!glyph) {
            cursorX += fontSize * 0.5f; // Default advance for missing glyphs
            continue;
        }
        
        // Skip drawing for space (but still advance)
        if (glyph->width > 0 && glyph->height > 0) {
            // Source rectangle in atlas (pixel coordinates)
            Rectangle source = {
                (float)glyph->x0,
                (float)glyph->y0,
                (float)glyph->width,
                (float)glyph->height
            };
            
            // Destination rectangle on screen
            Rectangle dest = {
                cursorX + glyph->xoff * scale,
                baseline + glyph->yoff * scale,
                glyph->width * scale,
                glyph->height * scale
            };
            
            DrawTexturePro(font->atlas, source, dest, (Vector2){0, 0}, 0.0f, color);
        }
        
        cursorX += glyph->advanceWidth * scale;
    }
    
    EndShaderMode();
}

float SdfFontMeasureText(SdfFont *font, const char *text, float fontSize) {
    if (!font || !text) return 0.0f;
    
    float scale = fontSize / (float)SDF_FONT_SIZE;
    float width = 0.0f;
    float maxWidth = 0.0f;
    
    for (const char *p = text; *p; p++) {
        int c = (unsigned char)*p;
        
        if (c == '\n') {
            if (width > maxWidth) maxWidth = width;
            width = 0.0f;
            continue;
        }
        
        SdfGlyphInfo *glyph = find_glyph(font, c);
        if (glyph) {
            width += glyph->advanceWidth * scale;
        } else {
            width += fontSize * 0.5f;
        }
    }
    
    return (width > maxWidth) ? width : maxWidth;
}

void SdfFontUnload(SdfFont *font) {
    if (!font) return;
    
    if (font->atlas.id > 0) {
        UnloadTexture(font->atlas);
    }
    if (font->shader.id > 0) {
        UnloadShader(font->shader);
    }
    
    *font = (SdfFont){0};
}

#endif // FONT_SDF_IMPLEMENTATION
