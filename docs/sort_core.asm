; Exact native SortDisplayObject selection rules, with direct cell traversal.
; EBX=list, EBP=last committed cell, ESI=remaining head, EDI=candidate.
; Native moved cells are recreated with flags=0/trans=1000. Match those fields
; while reusing the cell, avoiding both indexed rescans and heap churn.
push ebx
push ebp
push esi
push edi
sub esp, 12
mov ebx, ecx
xor ebp, ebp
mov esi, [ebx+4]
outer:
test esi, esi
jz done
mov edi, esi
candidate:
mov eax, [edi+8]
movzx edx, word ptr [eax+0x1c]
xor ecx, ecx
test edx, 0x100
jz class1
mov ecx, 1
class1:
test edx, 0x80
jz class2
mov ecx, 2
class2:
test edx, 0x20
jz class3
mov ecx, 3
class3:
mov [esp], ecx
mov edx, [eax+0x30]
add edx, [eax+4]
mov [esp+4], edx
mov edx, [eax+0x34]
add edx, [eax+8]
mov [esp+8], edx
mov ecx, esi
scan:
cmp ecx, edi
je next
mov eax, [ecx+8]
movzx edx, word ptr [eax+0x1c]
push ecx
xor ecx, ecx
test edx, 0x100
jz other1
mov ecx, 1
other1:
test edx, 0x80
jz other2
mov ecx, 2
other2:
test edx, 0x20
jz other3
mov ecx, 3
other3:
cmp ecx, [esp+4]
pop ecx
jg reject
jl next
mov edx, [eax+0x28]
add edx, [eax+4]
cmp [esp+4], edx
jle next
mov edx, [eax+0x2c]
add edx, [eax+8]
cmp [esp+8], edx
jle next
mov edx, [eax+0x30]
add edx, [eax+4]
cmp [esp+4], edx
jg reject
mov edx, [eax+0x34]
add edx, [eax+8]
cmp [esp+8], edx
jg reject
next:
mov ecx, [ecx+0x10]
test ecx, ecx
jnz scan
; Candidate has no blocker in the uncommitted suffix.
cmp edi, esi
je advance
mov eax, [edi+0xc]
mov edx, [edi+0x10]
mov [eax+0x10], edx
test edx, edx
jz no_next
mov [edx+0xc], eax
no_next:
mov [edi+0xc], ebp
mov [edi+0x10], esi
mov [esi+0xc], edi
test ebp, ebp
jz new_head
mov [ebp+0x10], edi
jmp reset_cell
new_head:
mov [ebx+4], edi
reset_cell:
mov word ptr [edi], 0
mov dword ptr [edi+4], 1000
mov ebp, edi
jmp outer
reject:
mov edi, [edi+0x10]
test edi, edi
jnz candidate
; Native leaves a cyclic/unsatisfied position as-is, then advances.
advance:
mov ebp, esi
mov esi, [esi+0x10]
jmp outer
done:
add esp, 12
pop edi
pop esi
pop ebp
pop ebx
mov eax, 1
