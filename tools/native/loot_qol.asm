; ShadowFlare 2.004 single-player loot QoL. All object mutations run on the
; original game thread. Quantities use the serialized, nonzero identification
; field of category 3 only; equipment identification is never touched.
;; @section update 0x0
pushfd
pushad
inc dword ptr [@data+36]
cmp dword ptr [0x482db0],0
jne update_done
mov edi,ecx
mov eax,[0x48ce0c]
test eax,eax
jz update_done
mov edx,[eax+8]
cmp edx,[eax]
jae update_done
mov eax,[eax+4]
cmp edi,[eax+edx*4]
jne update_done
cmp dword ptr [edi+0x1a4],0
jle update_done
cmp dword ptr [0x48ce34],0
jne update_done
cmp dword ptr [edi+0x404],0
jne update_done
cmp dword ptr [@data+48],0
je update_auto
mov dword ptr [@data+48],0
mov ecx,edi
call @normalize
update_auto:
cmp dword ptr [@data],1
jne update_done
call dword ptr [@data+40]
mov edx,eax
sub eax,[@data+32]
cmp eax,250
jb update_done
mov [@data+32],edx
mov ebx,[edi+0x458]
test ebx,ebx
jz update_done
mov eax,[ebx+0x14]
mov [@data+60],eax
mov eax,[ebx+0x30]
test eax,eax
jz update_done
mov esi,[eax+8]
update_loop:
test esi,esi
jz update_done
push dword ptr [esi+0xc]
cmp dword ptr [esi],3
jne update_next
mov eax,[esi+8]
test eax,eax
jz update_next
mov edx,[eax+4]
cmp edx,[@data+60]
jae update_next
mov ebp,[eax+0xcc]
test ebp,ebp
jz update_next
cmp dword ptr [ebp+0xc],3
je update_range
cmp dword ptr [ebp+0xc],4
jne update_next
cmp dword ptr [ebp+0x14],1
ja update_next
cmp dword ptr [ebp+0x14],0
jne update_range
call @sale_gold_ignored
test eax,eax
jnz update_next
update_range:
mov eax,[ebp+0x48]
sub eax,[edi+0x2e0]
cdq
xor eax,edx
sub eax,edx
push eax
mov eax,[ebp+0x4c]
sub eax,[edi+0x2e4]
cdq
xor eax,edx
sub eax,edx
pop edx
cmp eax,edx
jae update_axes
xchg eax,edx
update_axes:
imul eax,eax,170
imul edx,edx,70
add eax,edx
imul edx,dword ptr [@data+8],40800
cmp eax,edx
ja update_next
cmp dword ptr [ebp+0xc],4
jne update_pick
cmp dword ptr [ebp+0x14],1
jne update_pick
mov eax,[edi+0x328]
cmp eax,[edi+0x2c0]
jge update_next
update_pick:
push ebp
mov ecx,edi
call @can_accept
test eax,eax
jz update_next
; Hide only the inventory-open flag during the synchronous native pickup;
; otherwise the engine puts loot on the mouse cursor rather than in the bag.
push dword ptr [ebp+0x48]
push dword ptr [ebp+0x4c]
push dword ptr [0x48ce3c]
mov dword ptr [0x48ce3c],0
push ebp
push dword ptr [esi+8]
pop eax
push dword ptr [eax+4]
mov ecx,edi
call 0x449ef0
pop dword ptr [0x48ce3c]
cmp eax,1
jne update_restore
add esp,8
inc dword ptr [@data+12]
jmp update_next
update_restore:
; Native pickup removes the map entity before checking capacity. Restore the
; remaining object (including any partial gold/stack merge) on failure.
pop dword ptr [ebp+0x4c]
pop dword ptr [ebp+0x48]
push -1
push 0
push ebp
mov ecx,ebx
call 0x427970
update_next:
pop esi
jmp update_loop
update_done:
dec dword ptr [@data+36]
popad
popfd
mov esi,ecx
xor ebp,ebp
push edi
jmp 0x44349b

;; @section quantity 0x400
mov eax,1
cmp dword ptr [ecx+0xc],3
jne quantity_done
mov edx,[ecx+0x1c]
and edx,0xffff0000
cmp edx,0x53540000
jne quantity_done
mov eax,[ecx+0x1c]
and eax,0xffff
cmp eax,2
jb quantity_one
cmp eax,999
jbe quantity_done
quantity_one:
mov eax,1
quantity_done:
ret

;; @section setquantity 0x450
cmp eax,1
jbe setquantity_write
or eax,0x53540000
setquantity_write:
mov [ecx+0x1c],eax
ret

;; @section merge 0x480
; this=&head, arg=unlinked item. Return remaining pointer, or delete fully
; absorbed source and return zero. Never merges different exact template IDs.
push ebp
mov ebp,esp
sub esp,8
push ebx
push esi
push edi
mov esi,[ebp+8]
mov edi,[ecx]
mov ecx,esi
call @quantity
mov [ebp-4],eax
merge_loop:
test edi,edi
jz merge_remaining
cmp edi,esi
je merge_next
cmp dword ptr [edi+0xc],3
jne merge_next
mov eax,[edi+0x14]
cmp eax,[esi+0x14]
jne merge_next
mov ecx,edi
call @quantity
mov ebx,999
sub ebx,eax
jle merge_next
cmp ebx,[ebp-4]
jbe merge_amount
mov ebx,[ebp-4]
merge_amount:
add eax,ebx
mov ecx,edi
call @setquantity
sub [ebp-4],ebx
add [@data+16],ebx
cmp dword ptr [ebp-4],0
je merge_delete
merge_next:
mov edi,[edi+0x8c]
jmp merge_loop
merge_delete:
lea eax,[ebp+8]
push eax
mov ecx,[0x48ce14]
call 0x465640
xor eax,eax
jmp merge_done
merge_remaining:
mov eax,[ebp-4]
mov ecx,esi
call @setquantity
mov eax,esi
merge_done:
pop edi
pop esi
pop ebx
mov esp,ebp
pop ebp
ret 4

;; @section consume 0x600
pushfd
pushad
mov eax,[esp+36]
; Scenario DELETEITEM: one original item, now one unit of a consumable stack.
cmp eax,0x433d53
je consume_check
cmp eax,0x433d7b
je consume_check
cmp eax,0x442f62
je consume_check
cmp eax,0x443f26
je consume_check
cmp eax,0x44a6cf
je consume_check
cmp eax,0x44a6de
je consume_check
cmp eax,0x44a852
je consume_check
cmp eax,0x44ab3a
je consume_check
cmp eax,0x44acb4
je consume_check
cmp eax,0x44afee
jne consume_native
consume_check:
mov ebx,ecx
mov ecx,[esp+40]
test ecx,ecx
jz consume_native
; Verify actual list membership before changing a quantity.
mov edx,[ebx]
consume_find:
test edx,edx
jz consume_native
cmp edx,ecx
je consume_found
mov edx,[edx+0x8c]
jmp consume_find
consume_found:
call @quantity
cmp eax,1
jbe consume_native
dec eax
call @setquantity
inc dword ptr [@data+24]
popad
popfd
mov eax,1
ret 4
consume_native:
popad
popfd
push ecx
mov eax,[ecx]
xor edx,edx
jmp 0x466c45

;; @section price 0x700
push ebx
push ecx
call @quantity
mov ebx,eax
pop ecx
push dword ptr [esp+8]
call @price_original
imul eax,ebx
pop ebx
ret 4
;; @section price_original 0x740
sub esp,0xc
push ebx
push ebp
jmp 0x4661c5

;; @section draw 0x760
pushfd
pushad
mov ecx,esi
call @quantity
cmp eax,1
jbe draw_done
mov edx,[esp+0x44]
add edx,21
mov ecx,[esp+0x40]
add ecx,29
push 0
push edx
push ecx
push eax
push dword ptr [esp+0x4c]
push dword ptr [esp+0x4c]
mov ecx,esi
call 0x405590
draw_done:
popad
popfd
pop edi
pop esi
pop ebp
pop ebx
ret 0x1c

;; @section right 0x800
push ebp
mov ebp,esp
sub esp,8
push ebx
push esi
push edi
mov esi,ecx
cmp dword ptr [0x482db0],0
jne right_native
cmp dword ptr [0x48ce3c],1
jne right_native
cmp dword ptr [0x48ce34],0
jne right_native
cmp dword ptr [esi+0x404],0
jne right_native
push 16
call dword ptr [@data+44]
test ax,0x8000
jz right_native
mov eax,[esi+0x3fc]
lea edx,[ebp-8]
push edx
lea edx,[ebp-4]
push edx
push dword ptr [eax+4]
push dword ptr [eax]
mov ecx,esi
call 0x447290
cmp eax,9
jne right_native
push -1
push -1
push dword ptr [ebp-8]
push dword ptr [ebp-4]
lea ecx,[esi+0x514]
call 0x466b00
test eax,eax
jz right_native
mov edi,eax
mov ecx,eax
call @quantity
cmp eax,1
jbe right_native
mov ebx,eax
mov [esi+0x1570],edi
mov dword ptr [esi+0x1574],0
mov eax,[0x482778]
push 0
push 0
push 0x405
push eax
call dword ptr [0x473618]
mov eax,[0x482778]
push 0
push 0
push 0x403
push eax
call dword ptr [0x473618]
mov eax,[esi+0x3fc]
mov edx,[eax+4]
mov eax,[eax]
sub edx,24
sub eax,24
push ebx
push edx
push eax
mov ecx,esi
call 0x441ab0
mov eax,1
jmp right_done
right_native:
mov ecx,esi
call @right_original
right_done:
pop edi
pop esi
pop ebx
mov esp,ebp
pop ebp
ret
;; @section right_original 0xa00
push esi
mov esi,ecx
cmp dword ptr [esi+0x1624],1
jmp 0x445a4a

;; @section split 0xa20
pushfd
pushad
mov ebx,[esi+0x1570]
test ebx,ebx
jz split_native
cmp dword ptr [ebx+0xc],3
jne split_native
cmp dword ptr [esi+0x1574],0
jne split_cancel
cmp edi,1
jl split_cancel
cmp dword ptr [0x48ce34],0
jne split_cancel
mov eax,[esi+0x514]
split_find:
test eax,eax
jz split_cancel
cmp eax,ebx
je split_found
mov eax,[eax+0x8c]
jmp split_find
split_found:
mov ecx,ebx
call @quantity
cmp edi,eax
ja split_cancel
je split_whole
push eax
push 0
push dword ptr [ebx+0x14]
push 3
mov ecx,[0x48ce14]
call 0x462d30
pop edx
test eax,eax
jz split_cancel
mov [0x48ce34],eax
mov [@data+56],eax
mov ecx,eax
mov eax,edi
call @setquantity
mov ecx,ebx
call @quantity
sub eax,edi
call @setquantity
jmp split_success
split_whole:
push ebx
lea ecx,[esi+0x514]
call 0x466be0
mov [0x48ce34],ebx
mov [@data+56],ebx
split_success:
inc dword ptr [@data+20]
split_cancel:
popad
popfd
jmp 0x4433fb
split_native:
popad
popfd
mov ecx,[esi+0x1570]
jmp 0x443347

;; @section pickup 0xc00
pushfd
pushad
cmp dword ptr [@data+4],1
jne pickup_native
cmp dword ptr [0x48ce3c],0
jne pickup_native
mov eax,[esp+0x3c]
cmp dword ptr [eax+0xc],3
jne pickup_native
push eax
lea ecx,[edi+0x514]
call @merge
mov [esp+0x3c],eax
test eax,eax
jnz pickup_native
popad
popfd
jmp 0x449fb0
pickup_native:
popad
popfd
cmp dword ptr [0x48ce3c],1
jmp 0x449fc4

;; @section insert 0xd00
push ebx
push esi
mov ebx,ecx
mov esi,[esp+12]
cmp esi,[@data+56]
jne insert_check
mov dword ptr [@data+56],0
jmp insert_native
insert_check:
cmp dword ptr [@data+4],1
jne insert_native
cmp dword ptr [esi+0xc],3
jne insert_native
push esi
call @merge
test eax,eax
jz insert_done
mov esi,eax
insert_native:
push esi
mov ecx,ebx
call 0x466bc0
insert_done:
mov eax,1
pop esi
pop ebx
ret 4

;; @section normalize 0xe00
push ebx
push esi
push edi
mov edi,ecx
mov esi,[edi+0x514]
normalize_loop:
test esi,esi
jz normalize_done
mov ebx,[esi+0x8c]
cmp dword ptr [esi+0xc],3
jne normalize_next
push esi
lea ecx,[edi+0x514]
call 0x466be0
push esi
lea ecx,[edi+0x514]
call @merge
test eax,eax
jz normalize_next
push eax
lea ecx,[edi+0x514]
call 0x466bc0
normalize_next:
mov esi,ebx
jmp normalize_loop
normalize_done:
mov ecx,edi
call 0x450080
pop edi
pop esi
pop ebx
ret

;; @section ground_save 0xf00
; Ground consumable records have no identification field. Encode count in an
; otherwise invalid template ID, retaining the original 16-byte record size.
pushfd
pushad
mov ecx,[ebx+0xcc]
call @quantity
cmp eax,1
jbe ground_save_done
mov edi,eax
mov eax,[ecx+0x14]
xor edx,edx
mov ebp,10000000
div ebp
shl eax,4
or eax,edx
shl edi,7
or eax,edi
or eax,0x53000000
mov [esp+28],eax
ground_save_done:
popad
popfd
mov [esi+4],eax
mov ecx,[ebx+0xcc]
jmp 0x41b54a

;; @section factory 0x1000
cmp dword ptr [esp+4],3
jne factory_native
mov eax,[esp+8]
mov edx,eax
and edx,0xfffe0000
cmp edx,0x53000000
jne factory_native
push ebx
push esi
mov ebx,eax
shr ebx,7
and ebx,1023
cmp ebx,2
jb factory_invalid
cmp ebx,999
ja factory_invalid
and eax,127
mov edx,eax
and edx,15
shr eax,4
cmp eax,4
ja factory_invalid
cmp edx,9
ja factory_invalid
imul eax,eax,10000000
add eax,edx
push dword ptr [esp+20]
push eax
push 3
call @factory_original
test eax,eax
jz factory_done
mov esi,eax
mov ecx,eax
mov eax,ebx
call @setquantity
mov eax,esi
factory_done:
pop esi
pop ebx
ret 12
factory_invalid:
pop esi
pop ebx
factory_native:
jmp @factory_original
;; @section factory_original 0x1100
mov eax,dword ptr fs:[0]
jmp 0x462d36

;; @section can_accept 0x1200
; Read-only capacity preflight. A full bag never churns ground entities every
; polling pass. The native pickup still makes the final acceptance decision.
push ebp
mov ebp,esp
sub esp,8
push ebx
push esi
push edi
mov edi,ecx
mov esi,[ebp+8]
cmp dword ptr [esi+0xc],4
jne accept_potion
cmp dword ptr [esi+0x14],1
je accept_yes
mov ebx,[edi+0x514]
accept_gold_loop:
test ebx,ebx
jz accept_bag
cmp dword ptr [ebx+0xc],4
jne accept_gold_next
cmp dword ptr [ebx+0x14],0
jne accept_gold_next
cmp dword ptr [ebx+0x40],0x7fffffff
jb accept_yes
accept_gold_next:
mov ebx,[ebx+0x8c]
jmp accept_gold_loop
accept_potion:
cmp dword ptr [@data+4],1
jne accept_hotbar
mov ebx,[edi+0x514]
accept_stack_loop:
test ebx,ebx
jz accept_hotbar
cmp dword ptr [ebx+0xc],3
jne accept_stack_next
mov eax,[ebx+0x14]
cmp eax,[esi+0x14]
jne accept_stack_next
mov ecx,ebx
call @quantity
cmp eax,999
jb accept_yes
accept_stack_next:
mov ebx,[ebx+0x8c]
jmp accept_stack_loop
accept_hotbar:
cmp dword ptr [esi+0x94],0
je accept_bag
push 0
push 0
lea eax,[ebp-8]
push eax
push dword ptr [esi+0x24]
push dword ptr [esi+0x20]
push 2
push 4
lea ecx,[edi+0x518]
call 0x466f80
cmp eax,1
je accept_yes
accept_bag:
push 0
push 1
lea eax,[ebp-8]
push eax
push dword ptr [esi+0x24]
push dword ptr [esi+0x20]
push 4
push 9
lea ecx,[edi+0x514]
call 0x466f80
jmp accept_done
accept_yes:
mov eax,1
accept_done:
pop edi
pop esi
pop ebx
mov esp,ebp
pop ebp
ret 4

;; @section identified 0x1400
; Identify-all (4670d0) writes 1 to EVERY backpack/warehouse item. A counted
; consumable is already identified; an ordinary 0/1 flag update must never
; overwrite its quantity. Tagged save/load values still replace the count.
; Match the original setter's EAX return, EDX and incoming flags exactly.
mov eax,[esp+4]
pushfd
push edx
cmp eax,1
ja identified_write
cmp dword ptr [ecx+0xc],3
jne identified_write
mov edx,[ecx+0x1c]
and edx,0xffff0000
cmp edx,0x53540000
jne identified_write
mov edx,[ecx+0x1c]
and edx,0xffff
cmp edx,2
jb identified_write
cmp edx,999
ja identified_write
inc dword ptr [@data+64]
pop edx
popfd
ret 4
identified_write:
pop edx
popfd
mov [ecx+0x1c],eax
ret 4

;; @section sale_gold_ignored 0x1500
; Immutable table pointer + mutable identity binding, separate from save data.
; A normal gold bag at a reused address cannot inherit the exclusion.
push ebx
push esi
push edi
push ebp
mov ecx,[@data+68]
test ecx,ecx
jz sale_gold_no
mov eax,[ecx]
add ecx,4
sale_gold_scan:
test eax,eax
jz sale_gold_no
mov edx,[edi+0x10]
cmp edx,[ecx]
jne sale_gold_next
mov edx,[edi+0x14]
cmp edx,[ecx+4]
jne sale_gold_next
mov edx,[edi+0x18]
cmp edx,[ecx+8]
jne sale_gold_next
; The same name in a different save slot is a different owner.
push eax
mov eax,[0x482dcc]
test eax,eax
jz sale_gold_file_miss
mov edx,[eax]
test edx,edx
jz sale_gold_file_miss
mov eax,[edx]
cmp eax,[ecx+36]
jne sale_gold_file_miss
mov eax,[edx+4]
cmp eax,[ecx+40]
jne sale_gold_file_miss
mov eax,[edx+8]
cmp eax,[ecx+44]
jne sale_gold_file_miss
mov ax,[edx+12]
cmp ax,[ecx+48]
jne sale_gold_file_miss
pop eax
mov edx,[ebx+4]
cmp edx,[ecx+12]
jne sale_gold_next
mov edx,[ebp+0x48]
cmp edx,[ecx+16]
jne sale_gold_next
mov edx,[ebp+0x4c]
cmp edx,[ecx+20]
jne sale_gold_next
mov edx,[ebp+0x40]
cmp edx,[ecx+24]
jne sale_gold_next
mov edx,[esi+8]
mov edx,[edx+4]
cmp dword ptr [ecx+28],0
je sale_gold_bind
cmp [ecx+28],ebx
jne sale_gold_bind
cmp [ecx+32],edx
jne sale_gold_next
jmp sale_gold_yes
sale_gold_bind:
mov [ecx+28],ebx
mov [ecx+32],edx
sale_gold_yes:
inc dword ptr [@data+72]
mov eax,1
jmp sale_gold_done
sale_gold_next:
add ecx,52
dec eax
jmp sale_gold_scan
sale_gold_file_miss:
pop eax
jmp sale_gold_next
sale_gold_no:
xor eax,eax
sale_gold_done:
pop ebp
pop edi
pop esi
pop ebx
ret
