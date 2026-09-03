/*
 * Image Segmentation via Flood-Fill Clustering
 * 
 * Groups pixels by color similarity in HSV space using iterative
 * region growing. Each cluster expands from seed pixels using
 * stack-based traversal.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>
#include <raylib.h>
#include <raymath.h>

#define NOB_STRIP_PREFIX
#include "nob.h"

#define IMG_WIDTH 128
#define IMG_HEIGHT 128

typedef struct { int col, row; } Cell;
typedef struct { Cell *data; size_t len; size_t cap; } CellStack;
typedef struct { int *grid; int cols, rows; } IntMatrix;
typedef struct { Vector3 *grid; int cols, rows; } Vec3Matrix;
typedef struct { Color *grid; int cols, rows; } RgbaMatrix;

static inline int idx2d(int c, int r, int stride) { return r * stride + c; }
static inline bool valid_coords(int c, int r, int w, int h) {
    return c >= 0 && c < w && r >= 0 && r < h;
}

static void stack_push(CellStack *s, int c, int r) {
    if (s->len >= s->cap) {
        s->cap = s->cap ? s->cap * 2 : 256;
        s->data = realloc(s->data, s->cap * sizeof(Cell));
    }
    s->data[s->len++] = (Cell){c, r};
}

static Cell stack_pop(CellStack *s) {
    return s->data[--s->len];
}

static float wrap_hue_diff(float h1, float h2)
{
    float d = fabsf(h1 - h2);
    if (d > 180.0f) d = 360.0f - d;
    return d / 360.0f;
}

static bool colors_similar(Vector3 hsv1, Vector3 hsv2, float max_dist_sq)
{
    float hue_d = wrap_hue_diff(hsv1.x, hsv2.x);
    float sat_d = hsv1.y - hsv2.y;
    float val_d = hsv1.z - hsv2.z;
    float dist_sq = hue_d * hue_d + sat_d * sat_d + val_d * val_d;
    return dist_sq <= max_dist_sq;
}

static const int DIR_X[] = {1, -1, 0, 0, 1, -1, 1, -1};
static const int DIR_Y[] = {0, 0, 1, -1, 1, -1, -1, 1};
#define CONNECTIVITY 8
#define DENSITY_REQ 8

static int adjacent_similar_count(Vec3Matrix *hsv, int c, int r, float thresh_sq)
{
    int total = 0;
    Vector3 ref = hsv->grid[idx2d(c, r, hsv->cols)];
    for (int d = 0; d < CONNECTIVITY; d++) {
        int nc = c + DIR_X[d];
        int nr = r + DIR_Y[d];
        if (!valid_coords(nc, nr, hsv->cols, hsv->rows)) continue;
        if (colors_similar(ref, hsv->grid[idx2d(nc, nr, hsv->cols)], thresh_sq)) {
            total++;
        }
    }
    return total;
}

static const Color SEGMENT_COLORS[] = {
    {50, 205, 50, 255},    {135, 206, 235, 255}, {128, 0, 128, 255},
    {255, 0, 0, 255},      {245, 245, 220, 255}, {255, 215, 0, 255},
    {0, 0, 255, 255},      {0, 128, 0, 255},     {0, 0, 139, 255},
    {238, 130, 238, 255},  {255, 255, 0, 255},   {139, 69, 19, 255},
    {255, 0, 255, 255},    {48, 0, 48, 255},     {255, 165, 0, 255},
    {0, 100, 0, 255},      {139, 69, 19, 255},   {255, 192, 203, 255},
    {128, 0, 0, 255},
};
#define NUM_SEGMENT_COLORS (sizeof(SEGMENT_COLORS) / sizeof(SEGMENT_COLORS[0]))

static void perform_segmentation(Image src, float similarity, Texture2D *result)
{
    static RgbaMatrix rgba = {0};
    static Vec3Matrix hsv_cache = {0};
    static IntMatrix segment_ids = {0};
    static CellStack pending = {0};
    static CellStack expansion = {0};
    
    int w = src.width;
    int h = src.height;
    int total_pixels = w * h;
    
    if (rgba.grid) UnloadImageColors(rgba.grid);
    rgba.grid = LoadImageColors(src);
    rgba.cols = w;
    rgba.rows = h;
    
    if (!hsv_cache.grid || hsv_cache.cols != w || hsv_cache.rows != h) {
        hsv_cache.grid = realloc(hsv_cache.grid, total_pixels * sizeof(Vector3));
        hsv_cache.cols = w;
        hsv_cache.rows = h;
    }
    
    for (int i = 0; i < total_pixels; i++) {
        hsv_cache.grid[i] = ColorToHSV(rgba.grid[i]);
    }
    
    if (!segment_ids.grid || segment_ids.cols != w || segment_ids.rows != h) {
        segment_ids.grid = realloc(segment_ids.grid, total_pixels * sizeof(int));
        segment_ids.cols = w;
        segment_ids.rows = h;
    }
    
    for (int i = 0; i < total_pixels; i++) {
        segment_ids.grid[i] = -1;
    }
    
    float thresh_sq = similarity * similarity;
    int seg_id = 0;
    
    for (int start_r = 0; start_r < h; start_r++) {
        for (int start_c = 0; start_c < w; start_c++) {
            int start_idx = idx2d(start_c, start_r, w);
            
            if (segment_ids.grid[start_idx] != -1) continue;
            
            int neighbor_count = adjacent_similar_count(&hsv_cache, start_c, start_r, thresh_sq);
            
            if (neighbor_count + 1 < DENSITY_REQ) {
                segment_ids.grid[start_idx] = 0;
                continue;
            }
            
            seg_id++;
            pending.len = 0;
            stack_push(&pending, start_c, start_r);
            segment_ids.grid[start_idx] = seg_id;
            
            while (pending.len > 0) {
                expansion.len = 0;
                
                while (pending.len > 0) {
                    Cell cur = stack_pop(&pending);
                    
                    int cur_neighbors = adjacent_similar_count(&hsv_cache, cur.col, cur.row, thresh_sq);
                    if (cur_neighbors + 1 < DENSITY_REQ) continue;
                    
                    Vector3 cur_hsv = hsv_cache.grid[idx2d(cur.col, cur.row, w)];
                    
                    for (int d = 0; d < CONNECTIVITY; d++) {
                        int nc = cur.col + DIR_X[d];
                        int nr = cur.row + DIR_Y[d];
                        
                        if (!valid_coords(nc, nr, w, h)) continue;
                        
                        int nidx = idx2d(nc, nr, w);
                        if (segment_ids.grid[nidx] > 0) continue;
                        
                        Vector3 neighbor_hsv = hsv_cache.grid[nidx];
                        if (colors_similar(cur_hsv, neighbor_hsv, thresh_sq)) {
                            segment_ids.grid[nidx] = seg_id;
                            stack_push(&expansion, nc, nr);
                        }
                    }
                }
                
                CellStack tmp = pending;
                pending = expansion;
                expansion = tmp;
            }
        }
    }
    
    for (int i = 0; i < total_pixels; i++) {
        int sid = segment_ids.grid[i];
        if (sid <= 0) {
            rgba.grid[i] = BLACK;
        } else {
            rgba.grid[i] = SEGMENT_COLORS[sid % NUM_SEGMENT_COLORS];
        }
    }
    
    UnloadTexture(*result);
    *result = LoadTextureFromImage((Image){
        .data = rgba.grid,
        .width = w,
        .height = h,
        .mipmaps = 1,
        .format = PIXELFORMAT_UNCOMPRESSED_R8G8B8A8,
    });
}

int main(void)
{
    SetConfigFlags(FLAG_WINDOW_RESIZABLE);
    InitWindow(800, 600, "HSV Color Clustering");
    SetTargetFPS(60);

    Image input_img = LoadImage("broadway-128.png");
    Texture2D output_tex = LoadTextureFromImage(input_img);
    
    float sim_threshold = 0.3f;
    float adjustment = 0.01f;

    while (!WindowShouldClose()) {
        bool needs_update = false;
        
        if (IsKeyPressed(KEY_UP)) {
            sim_threshold += adjustment;
            needs_update = true;
        }
        if (IsKeyPressed(KEY_DOWN) && sim_threshold > adjustment) {
            sim_threshold -= adjustment;
            needs_update = true;
        }
        if (IsKeyPressed(KEY_SPACE)) {
            needs_update = true;
        }
        
        if (needs_update) {
            perform_segmentation(input_img, sim_threshold, &output_tex);
        }

        BeginDrawing();
        {
            ClearBackground(GetColor(0x181818FF));
            
            int screen_w = GetScreenWidth();
            int screen_h = GetScreenHeight();
            float fit_scale = fminf((float)screen_w / output_tex.width, 
                                    (float)screen_h / output_tex.height);
            
            DrawTextureEx(output_tex, (Vector2){0, 0}, 0, fit_scale, WHITE);
            DrawText(TextFormat("Threshold: %.2f", sim_threshold), 10, 10, 24, WHITE);
        }
        EndDrawing();
    }

    UnloadTexture(output_tex);
    UnloadImage(input_img);
    CloseWindow();
    return 0;
}
