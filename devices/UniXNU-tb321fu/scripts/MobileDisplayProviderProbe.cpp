// Taken from the reference port (UniXNU-sheng package/MobileDisplayProviderProbe.cpp).
// Device independent: it registers our class, builds the provider, asks the original
// client for the display dimensions, then releases everything.
// SPDX-License-Identifier: BSD-2-Clause-Patent
// Offline kernel-linked class initialization and genuine original client query.
// This does not publish a display, render, or replace a system display list.
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOLib.h>
#include <libkern/c++/OSMetaClass.h>
#include <pexpert/pexpert.h>
#include <mach/kmod.h>
extern "C" kmod_info_t g_kernel_kmod_info;
extern "C" void native_mobile_display_static_init(void)
    __asm__("__GLOBAL__sub_I_NativeMobileDisplay.cpp");
extern "C" IOService *native_mobile_display_create(void);
extern "C" {
volatile uint32_t native_mobile_provider_stage;
volatile int native_mobile_provider_meta_status = -1;
volatile int native_mobile_provider_query_status = -1;
volatile uint64_t native_mobile_provider_object;
volatile uint64_t native_mobile_provider_client;
volatile uint64_t native_mobile_provider_dimensions[2];
volatile uint64_t native_mobile_provider_expected[2];
volatile uint32_t native_mobile_provider_parent_match;
volatile uint32_t native_mobile_provider_released;
void native_mobile_display_provider_probe(void);
__attribute__((noinline)) void native_mobile_display_provider_checkpoint(void);
void native_mobile_display_provider_checkpoint(void) { __asm__ volatile("" ::: "memory"); }
void native_mobile_display_provider_probe(void) {
    // This code is linked into our kernel and therefore registers under its
    // actual kernel owner, after the original parent kext has initialized.
    // Only our object's initializer section is deferred; original bytes stay
    // unchanged. Normal standalone kext loading would initialize dependencies.
    native_mobile_provider_stage = 1;
    printf("XNU display: stage 1, preModLoad(%s)\n", g_kernel_kmod_info.name);
    void *handle = OSMetaClass::preModLoad(g_kernel_kmod_info.name);
    if (!handle) { printf("XNU display: preModLoad refused\n"); native_mobile_display_provider_checkpoint(); return; }
    native_mobile_display_static_init();
    native_mobile_provider_meta_status = OSMetaClass::postModLoad(handle);
    printf("XNU display: stage 2, postModLoad=%d\n", native_mobile_provider_meta_status);
    if (native_mobile_provider_meta_status) { native_mobile_display_provider_checkpoint(); return; }
    native_mobile_provider_stage = 2;
    IOService *provider = native_mobile_display_create();
    native_mobile_provider_object = (uintptr_t)provider;
    printf("XNU display: stage 3, provider=%p\n", provider);
    if (!provider) { native_mobile_display_provider_checkpoint(); return; }
    native_mobile_provider_parent_match = provider->metaCast("IOMobileFramebuffer") != nullptr;
    // Ask the provider itself, not through the client, so a zero answer says
    // whether the override or the original dispatch path is at fault.
    {
        uint32_t direct_width = 0, direct_height = 0;
        void **vtable = *(void ***)provider;
        typedef void (*dimensions_fn)(void *, uint32_t *, uint32_t *);
        // The vptr points straight at the first virtual slot; entry 249 is
        // getDisplayDimensions and 182 is beforeExternalMethod.
        dimensions_fn direct = (dimensions_fn)vtable[249];
        typedef IOReturn (*ready_fn)(void *);
        IOReturn ready = ((ready_fn)vtable[182])(provider);
        direct(provider, &direct_width, &direct_height);
        printf("XNU display: direct provider %ux%u, ready=%d, parent match %u\n",
               direct_width, direct_height, (int)ready, (unsigned)native_mobile_provider_parent_match);
    }
    PE_Video video = {};
    PE_current_console(&video);
    native_mobile_provider_expected[0] = video.v_width;
    native_mobile_provider_expected[1] = video.v_height;
    native_mobile_provider_stage = 3;
    IOUserClient *client = OSDynamicCast(IOUserClient,
        OSMetaClass::allocClassWithName("IOMobileFramebufferUserClient"));
    native_mobile_provider_client = (uintptr_t)client;
    bool attached = false, started = false;
    if (client && client->init() && (attached = client->attach(provider)) &&
        (started = client->start(provider))) {
        native_mobile_provider_stage = 4;
        uint64_t values[2] = {UINT64_MAX,UINT64_MAX};
        IOExternalMethodArguments arguments = {};
        arguments.scalarOutput = values;
        arguments.scalarOutputCount = 2;
        native_mobile_provider_query_status = client->externalMethod(8,&arguments,nullptr,nullptr,nullptr);
        printf("XNU display: stage 4, query=%d dimensions=%llux%llu (console %llux%llu)\n",
               native_mobile_provider_query_status,
               native_mobile_provider_dimensions[0], native_mobile_provider_dimensions[1],
               native_mobile_provider_expected[0], native_mobile_provider_expected[1]);
        native_mobile_provider_dimensions[0] = values[0];
        native_mobile_provider_dimensions[1] = values[1];
        native_mobile_provider_stage = 5;
    }
    if (started) client->stop(provider);
    if (attached) client->detach(provider);
    if (client) client->release();
    provider->release();
    native_mobile_provider_released = 1;
    printf("XNU display: stage 5, released, attached=%d started=%d\n", (int)attached, (int)started);
    native_mobile_display_provider_checkpoint();
}
}
