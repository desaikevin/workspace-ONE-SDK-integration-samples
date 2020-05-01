// Copyright 2020 VMware, Inc.
// SPDX-License-Identifier: BSD-2-Clause

package com.example.integrationguide;

import org.jetbrains.annotations.NotNull;

public class DynamicBrandApplication extends Application {
    @NotNull
    @Override
    public com.airwatch.login.branding.BrandingManager getBrandingManager() {
        return BitmapBrandingManager.getInstance(this);
    }

    @Override
    public int getNotificationIcon() {
        return R.drawable.brand_logo_onecolour;
    }
}