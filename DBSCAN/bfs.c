/*
 * BFS-based Image Clustering using HSV Color Proximity
 * 
 * Segments an image into color-based clusters using a DBSCAN-like approach
 * with BFS expansion. Pixels are grouped if their HSV colors are within
 * a configurable threshold.
 * 
 * Controls:
 *   UP    - Increase color threshold
 *   DOWN  - Decrease color threshold  
 *   SPACE - Recompute clustering
 */

 #include <stdio.h>
 #include <stdlib.h>
 #include <string.h>
 #include <math.h>
 #include <raylib.h>
 #include <raymath.h>
 
 #define NOB_STRIP_PREFIX
 #include "nob.h"
 
 // 8-connectivity neighborhood offsets
 static const int NEIGHBOR_OFFSETS[][2] = {
     {-1,  0}, { 1,  0},  // horizontal
     { 0, -1}, { 0,  1},  // vertical
     {-1, -1}, { 1,  1},  // diagonal
     {-1,  1}, { 1, -1},
 };
 #define NUM_NEIGHBORS ARRAY_LEN(NEIGHBOR_OFFSETS)
 #define MIN_CORE_POINTS NUM_NEIGHBORS
 
 // ------------------ Data Structures ------------------
 
 typedef struct {
     int x, y;
 } Point;
 
 static inline Point point(int x, int y) {
     return (Point){x, y};
 }
 
 typedef struct {
     Point *items;
     size_t count;
     size_t capacity;
 } PointList;
 
 typedef struct {
     int *items;
     size_t width, height;
 } LabelGrid;
 
 typedef struct {
     Color *items;
     size_t width, height;
 } ColorGrid;
 
 typedef struct {
     Vector3 *items;
     size_t width, height;
 } HsvGrid;
 
 #define GRID_AT(grid, x, y) (grid)->items[(y) * (grid)->width + (x)]
 #define GRID_RESIZE(grid, w, h) do { \
     (grid)->items = realloc((grid)->items, sizeof(*(grid)->items) * (w) * (h)); \
     (grid)->width = (w); \
     (grid)->height = (h); \
 } while(0)
 #define GRID_BOUNDS_CHECK(grid, x, y) \
     ((x) >= 0 && (size_t)(x) < (grid)->width && (y) >= 0 && (size_t)(y) < (grid)->height)
 
 // ------------------ Color Distance ------------------
 
 static float hue_angular_distance(float h1, float h2)
 {
     h1 = fmodf(h1 / 360.0f, 1.0f);
     h2 = fmodf(h2 / 360.0f, 1.0f);
     float diff = fabsf(h1 - h2);
     return (diff <= 0.5f) ? diff : (1.0f - diff);
 }
 
 static float hsv_distance_squared(Vector3 a, Vector3 b)
 {
     float dh = hue_angular_distance(a.x, b.x);
     float ds = a.y - b.y;
     float dv = a.z - b.z;
     return dh * dh + ds * ds + dv * dv;
 }
 
 // ------------------ Cluster Visualization Colors ------------------
 
 static const Color CLUSTER_PALETTE[] = {
     LIME, SKYBLUE, PURPLE, RED, BEIGE, GOLD, BLUE, GREEN,
     DARKBLUE, VIOLET, YELLOW, DARKBROWN, MAGENTA, DARKPURPLE,
     ORANGE, DARKGREEN, BROWN, PINK, MAROON,
 };
 #define PALETTE_SIZE ARRAY_LEN(CLUSTER_PALETTE)
 
 // ------------------ Clustering Algorithm ------------------
 
 static size_t count_similar_neighbors(HsvGrid *hsv, int cx, int cy, float threshold_sq)
 {
     size_t count = 0;
     Vector3 center_color = GRID_AT(hsv, cx, cy);
     
     for (size_t i = 0; i < NUM_NEIGHBORS; ++i) {
         int nx = cx + NEIGHBOR_OFFSETS[i][0];
         int ny = cy + NEIGHBOR_OFFSETS[i][1];
         if (GRID_BOUNDS_CHECK(hsv, nx, ny)) {
             if (hsv_distance_squared(center_color, GRID_AT(hsv, nx, ny)) <= threshold_sq) {
                 count++;
             }
         }
     }
     return count;
 }
 
 static void cluster_image(Image image, float threshold, Texture2D *out_texture)
 {
     static ColorGrid pixels = {0};
     static HsvGrid hsv = {0};
     static LabelGrid labels = {0};
     static PointList frontier = {0};
     static PointList next_frontier = {0};
 
     size_t width = image.width;
     size_t height = image.height;
     size_t pixel_count = width * height;
 
     // Load pixel data
     if (pixels.items) UnloadImageColors(pixels.items);
     pixels.items = LoadImageColors(image);
     pixels.width = width;
     pixels.height = height;
 
     // Pre-compute HSV values for all pixels
     GRID_RESIZE(&hsv, width, height);
     for (size_t i = 0; i < pixel_count; ++i) {
         hsv.items[i] = ColorToHSV(pixels.items[i]);
     }
 
     // Initialize all labels as unvisited (-1)
     GRID_RESIZE(&labels, width, height);
     memset(labels.items, 0xFF, pixel_count * sizeof(int));  // -1 for signed int
 
     float threshold_sq = threshold * threshold;
     int current_label = 1;
 
     // Main clustering loop
     while (1) {
         // Find next unlabeled seed point with enough neighbors
         frontier.count = 0;
         bool seed_found = false;
         
         for (size_t y = 0; !seed_found && y < height; ++y) {
             for (size_t x = 0; !seed_found && x < width; ++x) {
                 if (GRID_AT(&labels, x, y) >= 0) continue;
                 
                 size_t neighbors = count_similar_neighbors(&hsv, x, y, threshold_sq);
                 if (neighbors + 1 < MIN_CORE_POINTS) {
                     GRID_AT(&labels, x, y) = 0;  // Mark as noise
                 } else {
                     da_append(&frontier, point(x, y));
                     GRID_AT(&labels, x, y) = current_label;
                     seed_found = true;
                 }
             }
         }
 
         if (!seed_found) break;
 
         // BFS expansion from seed
         while (frontier.count > 0) {
             next_frontier.count = 0;
             
             da_foreach(Point, p, &frontier) {
                 if (count_similar_neighbors(&hsv, p->x, p->y, threshold_sq) + 1 < MIN_CORE_POINTS) {
                     continue;
                 }
                 
                 Vector3 center_color = GRID_AT(&hsv, p->x, p->y);
                 
                 for (size_t i = 0; i < NUM_NEIGHBORS; ++i) {
                     int nx = p->x + NEIGHBOR_OFFSETS[i][0];
                     int ny = p->y + NEIGHBOR_OFFSETS[i][1];
                     
                     if (!GRID_BOUNDS_CHECK(&labels, nx, ny)) continue;
                     if (GRID_AT(&labels, nx, ny) > 0) continue;
                     
                     if (hsv_distance_squared(center_color, GRID_AT(&hsv, nx, ny)) <= threshold_sq) {
                         GRID_AT(&labels, nx, ny) = current_label;
                         da_append(&next_frontier, point(nx, ny));
                     }
                 }
             }
             swap(PointList, frontier, next_frontier);
         }
         current_label++;
     }
 
     // Assign visualization colors based on cluster labels
     for (size_t i = 0; i < pixel_count; ++i) {
         int label = labels.items[i];
         pixels.items[i] = (label == 0) ? BLACK : CLUSTER_PALETTE[label % PALETTE_SIZE];
     }
 
     // Update output texture
     UnloadTexture(*out_texture);
     *out_texture = LoadTextureFromImage((Image){
         .data = pixels.items,
         .width = width,
         .height = height,
         .mipmaps = 1,
         .format = PIXELFORMAT_UNCOMPRESSED_R8G8B8A8,
     });
 }
 
 // ------------------ Main Application ------------------
 
 int main(void)
 {
     SetConfigFlags(FLAG_WINDOW_RESIZABLE);
     InitWindow(800, 600, "HSV Color Clustering");
     SetTargetFPS(60);
 
     Image source_image = LoadImage("broadway-128.png");
     Texture2D display_texture = LoadTextureFromImage(source_image);
     
     float threshold = 0.3f;
     const float THRESHOLD_STEP = 0.01f;
 
     while (!WindowShouldClose()) {
         // Handle input
         if (IsKeyPressed(KEY_UP)) {
             threshold += THRESHOLD_STEP;
             cluster_image(source_image, threshold, &display_texture);
         }
         if (IsKeyPressed(KEY_DOWN)) {
             if (threshold >= THRESHOLD_STEP) threshold -= THRESHOLD_STEP;
             cluster_image(source_image, threshold, &display_texture);
         }
         if (IsKeyPressed(KEY_SPACE)) {
             cluster_image(source_image, threshold, &display_texture);
         }
 
         // Render
         BeginDrawing();
         ClearBackground(GetColor(0x181818FF));
         
         float scale_x = (float)GetScreenWidth() / display_texture.width;
         float scale_y = (float)GetScreenHeight() / display_texture.height;
         float scale = fminf(scale_x, scale_y);
         DrawTextureEx(display_texture, Vector2Zero(), 0, scale, WHITE);
         
         DrawText(TextFormat("Threshold: %.2f", threshold), 10, 10, 24, WHITE);
         EndDrawing();
     }
 
     UnloadTexture(display_texture);
     UnloadImage(source_image);
     CloseWindow();
     return 0;
 }
 