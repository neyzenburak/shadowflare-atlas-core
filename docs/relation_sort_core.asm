; Exact native stable partial ordering, incrementally maintained as a bit graph.
; Metadata: cell,L,T,R,B,group,reserved,dirty/removed (32 bytes).
; Capacity C rounds up by 256 and grows without an object count cap.
; Scratch: metadata32C, permutation4C, working degrees4C, dirty pointers4C,
; input order4C, hash8H, active mask S, outgoing C*S and incoming C*S.
; H=nextpow2(2C), S=C/8. Inactive cached geometry is never rendered.
; Exact geometry multisets retain matrix slots across reordered or rebuilt objects.
; Constants: 11111111=VirtualAlloc,22222222=VirtualFree,13579bdf=fallback,
; 44444444=cache state. Eight independently owned, dynamically sized entries.
push ebp
mov ebp, esp
sub esp, 176
push ebx
push esi
push edi
mov [ebp-4], ecx
mov eax, [ecx+4]
xor edi, edi
count:
test eax, eax
jz counted
inc edi
mov eax, [eax+16]
jmp count
counted:
cmp edi, 32
jb fallback
cmp edi, 0x07ffffff
ja fallback
mov [ebp-8], edi
mov ebx, 0x44444444
mov [ebp-48], ebx
mov eax, 1
xchg [ebx], eax
test eax, eax
jnz fallback
lea esi, [ebx+32]
lea edx, [ebx+224]
lookup:
cmp [esi], ecx
je slot
add esi, 24
cmp esi, edx
jb lookup
mov eax, [ebx+4]
inc dword ptr [ebx+4]
and eax, 7
imul eax, eax, 24
lea esi, [ebx+eax+32]
slot:
mov [ebp-36], esi
mov eax, [esi+4]
test eax, eax
jz allocate
cmp [esi], ecx
jne allocate
cmp edi, [esi+8]
ja allocate
mov edx, [esi+8]
mov [ebp-148], edx
shr edx, 3
mov [ebp-52], edx
jmp setup
allocate:
mov eax, [ebp-8]
add eax, 255
and eax, -256
mov [ebp-148], eax
mov ecx, eax
shr ecx, 3
mov [ebp-52], ecx
mul ecx
test edx, edx
jnz fallback_unlock
add eax, eax
jc fallback_unlock
add eax, [ebp-52]
jc fallback_unlock
mov ebx, eax
imul eax, dword ptr [ebp-148], 48
jo fallback_unlock
add eax, ebx
jc fallback_unlock
mov ebx, 1
mov ecx, [ebp-148]
shl ecx, 1
hash_size:
cmp ebx, ecx
jae hash_sized
shl ebx, 1
jmp hash_size
hash_sized:
lea ecx, [ebx*8]
add eax, ecx
jc fallback_unlock
dec ebx
mov [ebp-96], ebx
push 4
push 0x3000
push eax
push 0
mov eax, 0x11111111
call eax
test eax, eax
jz fallback_unlock
mov [ebp-12], eax
mov esi, [ebp-36]
cmp dword ptr [esi+4], 0
je allocated
push 0x8000
push 0
push dword ptr [esi+4]
mov eax, 0x22222222
call eax
allocated:
mov eax, [ebp-12]
mov [esi+4], eax
mov ecx, [ebp-148]
mov [esi+8], ecx
mov dword ptr [esi+12], 0
mov ecx, [ebp-96]
mov [esi+16], ecx
mov dword ptr [esi+20], 0
setup:
mov [ebp-12], eax
mov ecx, [ebp-4]
mov [esi], ecx
mov ebx, [ecx+4]
mov esi, eax
mov eax, [ebp-148]
shl eax, 5
add eax, esi
mov [ebp-16], eax
mov [ebp-40], eax
mov ecx, [ebp-148]
shl ecx, 2
add eax, ecx
mov [ebp-56], eax
add eax, ecx
mov [ebp-60], eax
mov [ebp-64], eax
add eax, ecx
mov [ebp-84], eax
mov [ebp-88], eax
mov edx, [ebp-8]
lea edx, [eax+edx*4]
mov [ebp-160], edx
add eax, ecx
mov [ebp-92], eax
mov edx, [ebp-36]
mov ecx, [edx+16]
mov [ebp-96], ecx
inc ecx
shl ecx, 3
add eax, ecx
mov [ebp-156], eax
add eax, [ebp-52]
mov [ebp-68], eax
mov ecx, [ebp-148]
imul ecx, [ebp-52]
add eax, ecx
mov [ebp-152], eax
mov eax, [edx+20]
mov [ebp-100], eax
mov dword ptr [ebp-104], 0
cmp eax, [ebp-8]
je same_active_count
mov dword ptr [ebp-104], 1
same_active_count:
mov eax, [ebp-12]
mov [ebp-108], eax
; Build an exact geometry lookup. Native object addresses may be transient.
mov edi, [ebp-92]
mov ecx, [ebp-96]
inc ecx
shl ecx, 1
mov eax, [ebp-52]
shr eax, 2
add ecx, eax
xor eax, eax
cld
rep stosd
cmp dword ptr [ebp-100], 0
jne start_hash_build
mov eax, [ebp-48]
inc dword ptr [eax+20]
start_hash_build:
mov esi, [ebp-12]
hash_build:
mov dword ptr [esi+28], 0
cmp dword ptr [esi], 0
je hash_build_next
lea edx, [esi+4]
call geometry_hash
mov ecx, eax
and ecx, [ebp-96]
hash_insert:
mov edx, [ebp-92]
lea edx, [edx+ecx*8]
cmp dword ptr [edx+4], 0
je hash_inserted
inc ecx
and ecx, [ebp-96]
jmp hash_insert
hash_inserted:
mov [edx], eax
mov [edx+4], esi
hash_build_next:
add esi, 32
cmp esi, [ebp-16]
jb hash_build
snapshot:
call read_geometry
lea edx, [ebp-136]
call geometry_hash
mov ecx, eax
and ecx, [ebp-96]
hash_probe:
mov edx, [ebp-92]
lea edx, [edx+ecx*8]
mov esi, [edx+4]
test esi, esi
jz geometry_missing
cmp [edx], eax
jne probe_next
test dword ptr [esi+28], 2
jnz probe_next
mov edx, [ebp-136]
cmp [esi+4], edx
jne probe_next
mov edx, [ebp-132]
cmp [esi+8], edx
jne probe_next
mov edx, [ebp-128]
cmp [esi+12], edx
jne probe_next
mov edx, [ebp-124]
cmp [esi+16], edx
jne probe_next
mov edx, [ebp-120]
cmp [esi+20], edx
jne probe_next
mov dword ptr [esi+28], 2
mov [esi], ebx
mov edx, [ebp-88]
cmp [edx], esi
je matched_order
mov dword ptr [ebp-104], 1
matched_order:
mov [edx], esi
call mark_active
jmp snapshot_next
probe_next:
inc ecx
and ecx, [ebp-96]
jmp hash_probe
geometry_missing:
; Preserve the old input slot in dirty scratch until this ordinal is assigned.
mov ecx, [ebp-88]
mov edx, ecx
sub edx, [ebp-84]
add edx, [ebp-60]
mov eax, [ecx]
mov [edx], eax
mov eax, ebx
or eax, 1
mov [ecx], eax
snapshot_next:
add dword ptr [ebp-88], 4
mov ebx, [ebx+16]
test ebx, ebx
jnz snapshot
; Assign unmatched current geometry only after all unchanged records are claimed.
mov eax, [ebp-84]
mov [ebp-140], eax
assign_missing:
mov eax, [ebp-140]
mov ebx, [eax]
test ebx, 1
jz assign_next
and ebx, -2
call read_geometry
mov esi, [ebp-108]
find_unused:
test dword ptr [esi+28], 2
jz unused_found
add esi, 32
jmp find_unused
unused_found:
mov [ebp-108], esi
mov [esi], ebx
mov eax, [ebp-136]
mov [esi+4], eax
mov eax, [ebp-132]
mov [esi+8], eax
mov eax, [ebp-128]
mov [esi+12], eax
mov eax, [ebp-124]
mov [esi+16], eax
mov eax, [ebp-120]
mov [esi+20], eax
mov dword ptr [esi+28], 3
mov eax, [ebp-140]
mov edx, eax
sub edx, [ebp-84]
add edx, [ebp-60]
cmp [edx], esi
je assigned_order
mov dword ptr [ebp-104], 1
assigned_order:
mov [eax], esi
mov edx, [ebp-64]
mov [edx], esi
add dword ptr [ebp-64], 4
call mark_active
assign_next:
add dword ptr [ebp-140], 4
mov eax, [ebp-140]
cmp eax, [ebp-160]
jb assign_missing
mov eax, [ebp-36]
mov ecx, [ebp-8]
mov [eax+20], ecx
mov eax, [ebp-64]
sub eax, [ebp-60]
shr eax, 2
mov ecx, [ebp-48]
mov [ecx+16], eax
cmp dword ptr [ebp-104], 0
je counted_input
inc dword ptr [ecx+24]
counted_input:
mov esi, [ebp-12]
clear_visit_bits:
and dword ptr [esi+28], 1
add esi, 32
cmp esi, [ebp-16]
jb clear_visit_bits
mov dword ptr [ebp-72], 0
mov esi, [ebp-12]
mov ebx, [ebp-68]
update_row:
cmp dword ptr [esi+28], 0
je dirty_columns
mov edi, [ebp-12]
all_columns:
cmp esi, edi
je all_next
call update_edge
all_next:
add edi, 32
cmp edi, [ebp-16]
jb all_columns
jmp row_next
dirty_columns:
mov eax, [ebp-60]
mov [ebp-76], eax
dirty_column:
mov eax, [ebp-76]
cmp eax, [ebp-64]
jae row_next
mov edi, [eax]
cmp esi, edi
je dirty_next
call update_edge
dirty_next:
add dword ptr [ebp-76], 4
jmp dirty_column
row_next:
add ebx, [ebp-52]
add esi, 32
cmp esi, [ebp-16]
jb update_row
cmp dword ptr [ebp-72], 0
jne sort
cmp dword ptr [ebp-104], 0
jne sort
mov eax, [ebp-36]
cmp dword ptr [eax+12], 1
jne sort
mov eax, [ebp-48]
inc dword ptr [eax+8]
mov esi, [ebp-40]
mov edi, [ebp-8]
xor edx, edx
replay:
mov eax, [esi]
mov ecx, eax
and eax, -2
mov ebx, [eax]
test ecx, 1
jz replay_meta
mov word ptr [ebx], 0
mov dword ptr [ebx+4], 1000
replay_meta:
mov [ebx+12], edx
test edx, edx
jz replay_head
mov [edx+16], ebx
jmp replay_linked
replay_head:
mov ecx, [ebp-4]
mov [ecx+4], ebx
replay_linked:
mov edx, ebx
add esi, 4
dec edi
jnz replay
mov dword ptr [ebx+16], 0
jmp release_cache
sort:
mov eax, [ebp-48]
inc dword ptr [eax+12]
mov esi, [ebp-12]
init_work:
mov dword ptr [esi+28], 0
add esi, 32
cmp esi, [ebp-16]
jb init_work
; Indegrees consider active blockers only. The transposed matrix retains
; relations for inactive cached geometry without affecting native output.
mov eax, [ebp-84]
mov [ebp-140], eax
active_degree:
mov eax, [ebp-140]
mov eax, [eax]
sub eax, [ebp-12]
shr eax, 5
mov [ebp-164], eax
imul eax, [ebp-52]
add eax, [ebp-152]
mov edx, eax
mov ebx, [ebp-156]
mov edi, [ebp-52]
shr edi, 2
xor esi, esi
degree_word:
mov eax, [edx]
and eax, [ebx]
mov ecx, eax
shr ecx, 1
and ecx, 0x55555555
sub eax, ecx
mov ecx, eax
shr ecx, 2
and eax, 0x33333333
and ecx, 0x33333333
add eax, ecx
mov ecx, eax
shr ecx, 4
add eax, ecx
and eax, 0x0f0f0f0f
imul eax, eax, 0x01010101
shr eax, 24
add esi, eax
add edx, 4
add ebx, 4
dec edi
jnz degree_word
mov ecx, [ebp-56]
mov eax, [ebp-164]
mov [ecx+eax*4], esi
add dword ptr [ebp-140], 4
mov eax, [ebp-140]
cmp eax, [ebp-160]
jb active_degree
mov eax, [ebp-84]
mov [ebp-20], eax
mov dword ptr [ebp-24], 0
mov eax, [ebp-8]
mov [ebp-32], eax
mov eax, [ebp-40]
mov [ebp-44], eax
choose:
mov esi, [ebp-20]
find_zero:
mov edi, [esi]
cmp dword ptr [edi+28], 0
jne find_next
mov eax, edi
sub eax, [ebp-12]
shr eax, 3
mov ecx, [ebp-56]
cmp dword ptr [ecx+eax], 0
je selected
find_next:
add esi, 4
cmp esi, [ebp-160]
jb find_zero
mov eax, [ebp-20]
mov edi, [eax]
selected:
mov dword ptr [edi+28], 1
mov ebx, [edi]
mov eax, edi
mov ecx, [ebp-20]
cmp edi, [ecx]
je metadata_done
or eax, 1
mov word ptr [ebx], 0
mov dword ptr [ebx+4], 1000
metadata_done:
mov ecx, [ebp-44]
mov [ecx], eax
add dword ptr [ebp-44], 4
mov eax, [ebp-24]
mov [ebx+12], eax
test eax, eax
jz head
mov [eax+16], ebx
jmp linked
head:
mov ecx, [ebp-4]
mov [ecx+4], ebx
linked:
mov [ebp-24], ebx
mov eax, edi
sub eax, [ebp-12]
shr eax, 5
mul dword ptr [ebp-52]
add eax, [ebp-68]
mov esi, eax
add eax, [ebp-52]
mov [ebp-80], eax
xor edi, edi
mov eax, [ebp-156]
mov [ebp-172], eax
remove_word:
mov edx, [esi]
mov ecx, [ebp-172]
and edx, [ecx]
test edx, edx
jz word_next
remove_bit:
bsf eax, edx
btr edx, eax
add eax, edi
mov ecx, [ebp-56]
dec dword ptr [ecx+eax*4]
test edx, edx
jnz remove_bit
word_next:
add dword ptr [ebp-172], 4
add esi, 4
add edi, 32
cmp esi, [ebp-80]
jb remove_word
mov edi, [ebp-20]
first:
cmp edi, [ebp-160]
jae first_found
mov eax, [edi]
cmp dword ptr [eax+28], 0
je first_found
add edi, 4
jmp first
first_found:
mov [ebp-20], edi
dec dword ptr [ebp-32]
jnz choose
mov dword ptr [ebx+16], 0
mov eax, [ebp-36]
mov dword ptr [eax+12], 1
release_cache:
mov eax, [ebp-48]
mov dword ptr [eax], 0
pop edi
pop esi
pop ebx
mov esp, ebp
pop ebp
mov eax, 1
ret
fallback_unlock:
mov eax, [ebp-48]
mov dword ptr [eax], 0
fallback:
mov ecx, [ebp-4]
pop edi
pop esi
pop ebx
mov esp, ebp
pop ebp
mov eax, 0x13579bdf
jmp eax
update_edge:
call blocks
mov edx, eax
mov ecx, edi
sub ecx, [ebp-12]
shr ecx, 5
bt [ebx], ecx
sbb eax, eax
and eax, 1
cmp eax, edx
je edge_done
push edx
mov eax, esi
sub eax, [ebp-12]
shr eax, 5
mov edx, [ebp-156]
bt [edx], ecx
jnc inactive_edge
bt [edx], eax
jnc inactive_edge
mov dword ptr [ebp-72], 1
inactive_edge:
pop edx
test edx, edx
jz clear_edge
bts [ebx], ecx
mov eax, ecx
imul eax, [ebp-52]
add eax, [ebp-152]
mov edx, esi
sub edx, [ebp-12]
shr edx, 5
bts [eax], edx
ret
clear_edge:
btr [ebx], ecx
mov eax, ecx
imul eax, [ebp-52]
add eax, [ebp-152]
mov edx, esi
sub edx, [ebp-12]
shr edx, 5
btr [eax], edx
edge_done:
ret
blocks:
mov eax, [esi+20]
cmp eax, [edi+20]
jg yes
jl no
mov eax, [edi+12]
cmp eax, [esi+4]
jle no
mov edx, [edi+16]
cmp edx, [esi+8]
jle no
cmp eax, [esi+12]
jg yes
cmp edx, [esi+16]
jg yes
no:
xor eax, eax
ret
yes:
mov eax, 1
ret

read_geometry:
mov eax, [ebx+8]
mov ecx, [eax+4]
mov edx, [eax+8]
mov edi, [eax+0x28]
add edi, ecx
mov [ebp-136], edi
mov edi, [eax+0x2c]
add edi, edx
mov [ebp-132], edi
mov edi, [eax+0x30]
add edi, ecx
mov [ebp-128], edi
mov edi, [eax+0x34]
add edi, edx
mov [ebp-124], edi
movzx eax, word ptr [eax+0x1c]
xor ecx, ecx
test eax, 0x100
jz geom_group1
mov ecx, 1
geom_group1:
test eax, 0x80
jz geom_group2
mov ecx, 2
geom_group2:
test eax, 0x20
jz geom_group3
mov ecx, 3
geom_group3:
mov [ebp-120], ecx
ret
geometry_hash:
mov eax, [edx]
rol eax, 7
xor eax, [edx+4]
rol eax, 7
xor eax, [edx+8]
rol eax, 7
xor eax, [edx+12]
rol eax, 7
xor eax, [edx+16]
imul eax, eax, 0x9e3779b1
ret

mark_active:
mov eax, esi
sub eax, [ebp-12]
shr eax, 5
mov edx, [ebp-156]
bts [edx], eax
ret
