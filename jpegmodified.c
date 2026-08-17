/*
 * Behavioural reproducer for dangling pointer use-after-free
 * Observed in JPEGCleanup() inside coders/jpeg.c (ImageMagick)
 *
 * This program is an independent reimplementation of the pointer lifecycle.
 * It does NOT include or link against original ImageMagick source code.
 * A controlled error recovery path is constructed to deterministically
 * exercise the memory safety flaw for ASan validation.
 */
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>

/* Analogous structures mirroring layout observed in coders/jpeg.c */
typedef struct _JPEGClientInfo
{
    int decoder_status;
    char payload[256];  // Larger allocation helps ASan detect freed block reliably
} JPEGClientInfo;

typedef struct jpeg_decompress_struct
{
    void *client_data;
} jpeg_decompress_struct;

static void RelinquishMagickMemory(void *ptr)
{
    free(ptr);
}

static JPEGClientInfo *JPEGCleanup(jpeg_decompress_struct *cinfo,
                                   JPEGClientInfo *client_info)
{
    if (client_info != NULL)
    {
        RelinquishMagickMemory(client_info);
        /* Vulnerability: pointer is not nulled after deallocation */
    }
    return client_info;
}

int main(void)
{
    jmp_buf error_context;
    jpeg_decompress_struct cinfo;
    JPEGClientInfo *client_info;

    client_info = (JPEGClientInfo *)malloc(sizeof(JPEGClientInfo));
    if (client_info == NULL)
        return 1;

    if (setjmp(error_context) != 0)
    {
        /* Enter error recovery branch after decoding failure */
        client_info = JPEGCleanup(&cinfo, client_info);
        cinfo.client_data = client_info;

        /* Use-after-free occurs here via stale pointer stored in client_data */
        JPEGClientInfo *stale_reference = (JPEGClientInfo *)cinfo.client_data;
        stale_reference->decoder_status = 1;

        printf("Decoder status updated (UAF triggered)\n");
        fflush(stdout);
        return 1;
    }

    /* Simulate fatal parsing error that triggers longjmp in real decoder */
    longjmp(error_context, 1);
    return 0;
}

