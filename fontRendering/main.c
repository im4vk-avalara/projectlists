/*
 * SDF Font Renderer Demo
 * Copyright (c) 2026 Avinash Kumar. All rights reserved.
 *
 * Demonstrates the from-scratch SDF font rendering system.
 * Press UP/DOWN to change font size, showing smooth scaling.
 * Press G to view all glyphs in a grid.
 * Press TAB to view the font atlas texture.
 */

#include <raylib.h>
#include <stdio.h>

#define FONT_SDF_IMPLEMENTATION
#include "font_sdf.h"

// View modes
typedef enum {
    VIEW_DEMO = 0,      // Normal demo text
    VIEW_GLYPHS,        // Glyph grid viewer
    VIEW_ATLAS          // Raw atlas texture
} ViewMode;

int main(void)
{
    // Initialize window
    const int screenWidth = 1024;
    const int screenHeight = 768;
    
    SetConfigFlags(FLAG_MSAA_4X_HINT);
    InitWindow(screenWidth, screenHeight, "SDF Font Renderer - Glyph Viewer");
    SetTargetFPS(60);
    
    // Load SDF font from TTF file
    SdfFont font = SdfFontLoad("Vollkorn-Regular.ttf");
    
    if (font.glyphCount == 0) {
        TraceLog(LOG_ERROR, "Failed to load font!");
        CloseWindow();
        return 1;
    }
    
    float fontSize = 48.0f;
    float minSize = 12.0f;
    float maxSize = 200.0f;
    
    ViewMode viewMode = VIEW_DEMO;
    int selectedGlyph = -1;  // Currently hovered glyph in grid view
    float glyphSize = 64.0f; // Size of each glyph cell in grid view
    Vector2 glyphScroll = {0, 0}; // Scroll offset for glyph view
    
    while (!WindowShouldClose())
    {
        // Input
        if (IsKeyDown(KEY_UP)) fontSize += 100.0f * GetFrameTime();
        if (IsKeyDown(KEY_DOWN)) fontSize -= 100.0f * GetFrameTime();
        if (fontSize < minSize) fontSize = minSize;
        if (fontSize > maxSize) fontSize = maxSize;
        
        // Mode switching
        if (IsKeyPressed(KEY_TAB)) {
            viewMode = (viewMode == VIEW_ATLAS) ? VIEW_DEMO : VIEW_ATLAS;
        }
        if (IsKeyPressed(KEY_G)) {
            viewMode = (viewMode == VIEW_GLYPHS) ? VIEW_DEMO : VIEW_GLYPHS;
        }
        
        // Glyph view controls
        if (viewMode == VIEW_GLYPHS) {
            // Scroll with mouse wheel
            glyphScroll.y += GetMouseWheelMove() * 50.0f;
            if (glyphScroll.y > 0) glyphScroll.y = 0;
            
            // Adjust glyph cell size with +/-
            if (IsKeyPressed(KEY_EQUAL) || IsKeyPressed(KEY_KP_ADD)) glyphSize += 16.0f;
            if (IsKeyPressed(KEY_MINUS) || IsKeyPressed(KEY_KP_SUBTRACT)) glyphSize -= 16.0f;
            if (glyphSize < 32.0f) glyphSize = 32.0f;
            if (glyphSize > 128.0f) glyphSize = 128.0f;
        }
        
        // Drawing
        BeginDrawing();
        ClearBackground((Color){ 30, 30, 40, 255 });
        
        if (viewMode == VIEW_ATLAS) {
            // Debug view: show the font atlas
            DrawTexture(font.atlas, 10, 10, WHITE);
            DrawText("Font Atlas (TAB to toggle, G for glyph grid)", 10, font.atlas.height + 20, 20, GRAY);
            
        } else if (viewMode == VIEW_GLYPHS) {
            // Glyph grid viewer - render each character individually
            float padding = 10.0f;
            float cellSize = glyphSize + padding;
            int cols = (int)((screenWidth - 40) / cellSize);
            if (cols < 1) cols = 1;
            
            float startX = 20.0f;
            float startY = 60.0f + glyphScroll.y;
            
            // Title
            DrawText("Glyph Viewer - All Characters from TTF", 20, 15, 24, WHITE);
            DrawText(TextFormat("Total glyphs: %d | Cell size: %.0f | Scroll: Mouse wheel | +/-: Resize", 
                     font.glyphCount, glyphSize), 20, 42, 16, GRAY);
            
            selectedGlyph = -1;
            Vector2 mouse = GetMousePosition();
            
            for (int i = 0; i < font.glyphCount; i++) {
                int col = i % cols;
                int row = i / cols;
                
                float cellX = startX + col * cellSize;
                float cellY = startY + row * cellSize;
                
                // Skip if off screen
                if (cellY + cellSize < 50 || cellY > screenHeight) continue;
                
                // Check if mouse is hovering this cell
                Rectangle cellRect = { cellX, cellY, cellSize - padding/2, cellSize - padding/2 };
                bool isHovered = CheckCollisionPointRec(mouse, cellRect);
                if (isHovered) selectedGlyph = i;
                
                // Draw cell background
                Color bgColor = isHovered ? (Color){ 60, 80, 120, 255 } : (Color){ 45, 45, 55, 255 };
                DrawRectangleRec(cellRect, bgColor);
                DrawRectangleLinesEx(cellRect, 1.0f, (Color){ 70, 70, 80, 255 });
                
                // Get the character for this glyph
                char charStr[2] = { (char)font.glyphs[i].codepoint, '\0' };
                
                // Draw the glyph centered in the cell
                float charSize = glyphSize * 0.7f;
                float textWidth = SdfFontMeasureText(&font, charStr, charSize);
                float textX = cellX + (cellSize - padding/2 - textWidth) / 2;
                float textY = cellY + (cellSize - padding/2 - charSize) / 2;
                
                Color glyphColor = isHovered ? (Color){ 255, 220, 100, 255 } : WHITE;
                SdfFontDrawText(&font, charStr, textX, textY, charSize, glyphColor);
            }
            
            // Draw info panel for selected glyph
            if (selectedGlyph >= 0 && selectedGlyph < font.glyphCount) {
                SdfGlyphInfo *g = &font.glyphs[selectedGlyph];
                
                // Info panel at bottom
                Rectangle infoRect = { 10, screenHeight - 100, screenWidth - 20, 90 };
                DrawRectangleRec(infoRect, (Color){ 20, 20, 30, 240 });
                DrawRectangleLinesEx(infoRect, 2.0f, (Color){ 100, 150, 255, 255 });
                
                // Character preview (large)
                char charStr[2] = { (char)g->codepoint, '\0' };
                SdfFontDrawText(&font, charStr, 30, screenHeight - 90, 60, (Color){ 255, 220, 100, 255 });
                
                // Glyph info
                DrawText(TextFormat("Codepoint: %d (0x%02X) '%c'", g->codepoint, g->codepoint, 
                         (g->codepoint >= 32 && g->codepoint < 127) ? g->codepoint : '?'), 
                         120, screenHeight - 90, 18, WHITE);
                DrawText(TextFormat("Advance Width: %.2f | Left Bearing: %.2f", 
                         g->advanceWidth, g->leftBearing), 120, screenHeight - 68, 16, LIGHTGRAY);
                DrawText(TextFormat("Bitmap Size: %d x %d | Offset: (%d, %d)", 
                         g->width, g->height, g->xoff, g->yoff), 120, screenHeight - 48, 16, LIGHTGRAY);
                DrawText(TextFormat("Atlas Position: (%d, %d) to (%d, %d)", 
                         g->x0, g->y0, g->x1, g->y1), 120, screenHeight - 28, 16, LIGHTGRAY);
            }
            
            // Instructions
            DrawText("G: Back to demo | TAB: Atlas view | +/-: Resize cells | Scroll: Mouse wheel", 
                     20, screenHeight - 115, 14, (Color){ 150, 150, 150, 255 });
            
        } else {
            // Demo text rendering
            float y = 80.0f;
            
            // Title
            SdfFontDrawText(&font, "SDF Font Renderer", 50, y, fontSize, WHITE);
            y += fontSize * 1.5f;
            
            // Subtitle
            SdfFontDrawText(&font, "Using stb_truetype for TTF parsing", 50, y, fontSize * 0.6f, (Color){ 150, 200, 255, 255 });
            y += fontSize * 1.2f;
            
            // Sample text at current size
            SdfFontDrawText(&font, "The quick brown fox jumps", 50, y, fontSize * 0.5f, (Color){ 255, 220, 150, 255 });
            y += fontSize * 0.7f;
            
            SdfFontDrawText(&font, "over the lazy dog.", 50, y, fontSize * 0.5f, (Color){ 255, 220, 150, 255 });
            y += fontSize;
            
            // Show different sizes
            const char *sizeDemo = "Scalable!";
            float demoY = y + 20;
            float demoX = 50;
            
            for (float s = 16; s <= 72; s += 14) {
                SdfFontDrawText(&font, sizeDemo, demoX, demoY, s, 
                    (Color){ (unsigned char)(100 + s * 2), (unsigned char)(200 - s), (unsigned char)(150 + s), 255 });
                demoX += SdfFontMeasureText(&font, sizeDemo, s) + 20;
                if (demoX > screenWidth - 200) {
                    demoX = 50;
                    demoY += 80;
                }
            }
            
            // Instructions
            DrawText("UP/DOWN: Size | G: Glyph viewer | TAB: Atlas", 10, screenHeight - 30, 18, GRAY);
            DrawText(TextFormat("Font Size: %.1f", fontSize), screenWidth - 180, screenHeight - 30, 18, GRAY);
        }
        
        DrawFPS(screenWidth - 90, 10);
        
        EndDrawing();
    }
    
    // Cleanup
    SdfFontUnload(&font);
    CloseWindow();
    
    return 0;
}
