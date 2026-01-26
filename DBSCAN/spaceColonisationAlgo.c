#include <raylib.h>
#include <raymath.h>
#define NOB_STRIP_PREFIX
#include "nob.h"

typedef struct {
    size_t *items;
    size_t count;
    size_t capacity;
} Indices;

typedef struct {
    Vector2 *items;
    size_t count;
    size_t capacity;
} Points;

typedef struct {
    Vector2 position;
    Vector2 direction;
} Vein;

typedef struct {
    Vein *items;
    size_t count;
    size_t capacity;
} Veins;

Points auxins = {0};
Veins veins  = {0};

#define VEIN_RADIUS 5
#define VEIN_COLOR WHITE
#define VEIN_CORE_COLOR BLACK
#define AUXINS_RATE 20
#define AUXIN_RADIUS VEIN_RADIUS
#define AUXIN_COLOR RED
#define AUXIMITY 30

void spray_auxins(void)
{
    int w = GetScreenWidth();
    int h = GetScreenHeight();

    for (size_t i = 0; i < AUXINS_RATE; ++i) {
        Vector2 p;
        p.x = GetRandomValue(0, w);
        p.y = GetRandomValue(0, h);
        da_append(&auxins, p);
    }
}

void kill_auxins_by_auximity(void)
{
    static Indices to_remove = {0};
    to_remove.count = 0;
    da_foreach(Vector2, auxin, &auxins) {
        size_t index = auxin - auxins.items;
        da_foreach(Vein, vein, &veins) {
            if (Vector2Distance(*auxin, vein->position) <= AUXIMITY) {
                da_append(&to_remove, index);
                break;
            }
        }
    }
    while (to_remove.count > 0) {
        da_remove_unordered(&auxins, da_last(&to_remove));
        to_remove.count -= 1;
    }
}

void calculate_growth_directions(void)
{
    if (veins.count > 0) {
        da_foreach(Vein, vein, &veins) {
            vein->direction = Vector2Zero();
        }

        da_foreach(Vector2, auxin, &auxins) {
            Vein *cvein = &veins.items[0];
            for (size_t index = 1; index < veins.count; ++index) {
                Vein *vein = &veins.items[index];
                Vector2 a = vein->position;
                Vector2 b = cvein->position;
                if (Vector2Distance(a, *auxin) < Vector2Distance(b, *auxin)) {
                    cvein = vein;
                }
            }

            cvein->direction = Vector2Add(cvein->direction, Vector2Subtract(*auxin, cvein->position));
        }

        da_foreach(Vein, vein, &veins) {
            vein->direction = Vector2Normalize(vein->direction);
        }
    }
}

void grow_new_veins(void)
{
    static Points new_veins = {0};
    new_veins.count = 0;
    da_foreach(Vein, vein, &veins) {
        if (vein->direction.x == 0.0f && vein->direction.y == 0.0f) continue;
        Vector2 new_vein = {0};
        new_vein.x = vein->position.x + vein->direction.x*VEIN_RADIUS*2;
        new_vein.y = vein->position.y + vein->direction.y*VEIN_RADIUS*2;
        da_append(&new_veins, new_vein);
    }
    da_foreach(Vector2, position, &new_veins) {
        Vein new_vein = {
            .position = *position,
        };
        da_append(&veins, new_vein);
    }
}

int main(void)
{
    InitWindow(800, 600, "Raylib Template");
    SetTargetFPS(60);

    {
        int w = GetScreenWidth();
        int h = GetScreenHeight();
        Vein vein = {0};
        vein.position.x = w/2;
        vein.position.y = h*2/3;
        da_append(&veins, vein);
    }

    spray_auxins();
    kill_auxins_by_auximity();

    while (!WindowShouldClose()) {
        if (IsKeyPressed(KEY_SPACE)) {
            calculate_growth_directions();
            grow_new_veins();
            kill_auxins_by_auximity();
            spray_auxins();
            kill_auxins_by_auximity();
        }

        BeginDrawing(); {
            ClearBackground(GetColor(0x181818FF));
            da_foreach(Vein, vein, &veins) {
                DrawCircle(vein->position.x, vein->position.y, VEIN_RADIUS, VEIN_COLOR);
                DrawCircle(vein->position.x, vein->position.y, VEIN_RADIUS/2, VEIN_CORE_COLOR);

                DrawLineV(vein->position, Vector2Add(vein->position, Vector2Scale(vein->direction, 20)), PURPLE);
            }
            for (size_t i = 0; i < auxins.count; ++i) {
                Vector2 p = auxins.items[i];
                DrawCircle(p.x, p.y, AUXIN_RADIUS, AUXIN_COLOR);
                if (0) {
                    DrawRing(p, AUXIMITY, AUXIMITY + 2, 0, 360, 69, AUXIN_COLOR);
                }
            }
        } EndDrawing();
    }
    CloseWindow();
    return 0;
}