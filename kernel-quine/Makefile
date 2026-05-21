IMAGE    := kernel-quine-nasm
PLATFORM := linux/amd64
DRUN     := docker run --rm --platform $(PLATFORM) -v "$(CURDIR)":/work $(IMAGE)
DRUN_IT  := docker run --rm -it --platform $(PLATFORM) -v "$(CURDIR)":/work $(IMAGE)

.PHONY: image hello quine verify sanity shell clean run gen

# Build the Docker image (nasm + binutils on alpine).
image:
	docker build --platform $(PLATFORM) -t $(IMAGE) .

# Generic build+run. Usage: make run NAME=hello
run:
	$(DRUN) sh -c 'nasm -f elf64 $(NAME).asm -o $(NAME).o && ld $(NAME).o -o $(NAME) && ./$(NAME)'

hello:
	$(MAKE) run NAME=hello

quine:
	$(MAKE) run NAME=quine

# Re-derive quine.asm from the scaffolding template. Not needed for normal
# builds — quine.asm is the committed deliverable. Use this only when
# modifying the design.
gen:
	python3 scaffolding/fill_quine.py < scaffolding/quine_template.asm > quine.asm

# The quine verification: output must be byte-identical to source.
verify:
	$(DRUN) sh -c 'nasm -f elf64 quine.asm -o quine.o && ld quine.o -o quine && ./quine | diff - quine.asm && echo "QUINE OK"'

# Verbose sanity check: byte counts side-by-side, diff, exit code.
sanity:
	$(DRUN) sh -c 'nasm -f elf64 quine.asm -o quine.o && ld quine.o -o quine && \
	    echo "--- byte counts ---" && \
	    printf "quine output : %s bytes\n" "$$(./quine | wc -c | tr -d " ")" && \
	    printf "quine.asm    : %s bytes\n" "$$(wc -c < quine.asm | tr -d " ")" && \
	    echo "--- diff ./quine vs quine.asm ---" && \
	    ./quine | diff - quine.asm && \
	    echo "--- exit code of quine binary ---" && \
	    ./quine > /dev/null; echo "exit=$$?" && \
	    echo "QUINE OK"'

# Interactive shell in the container.
shell:
	$(DRUN_IT) sh

clean:
	rm -f *.o hello quine
